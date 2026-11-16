"""Stdio JSON-lines worker entry point.

The worker announces readiness, emits heartbeats, answers pings, and runs
recognition requests. Recognition imports NumPy, OpenCV, and PaddleOCR
lazily so the lifecycle path still starts quickly and without the optional
OCR dependencies installed.

Analysis runs on the stdin read loop. Heartbeats run on their own thread,
so the desktop supervisor still sees the process alive during a long OCR
call or first model load. Requests are serialized: one analysis at a time.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import threading
import time
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence, TextIO

SCHEMA_VERSION = 1
WORKER_VERSION = "0.2.0"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 2.0
DEFAULT_PREPROCESS_MODE = "upscale3x_adaptive"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


class WorkerServer:
    """A single-process, single-connection JSON-lines server."""

    def __init__(
        self,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        ocr_mode: str = "paddle",
        ocr_lines_path: str | None = None,
        lang: str = "ru",
        model_dir: str | None = None,
        enable_mkldnn: bool = False,
    ) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        self._heartbeat_interval = max(0.01, heartbeat_interval)
        self._ocr_mode = ocr_mode
        self._ocr_lines_path = ocr_lines_path
        self._lang = lang
        self._model_dir = model_dir
        self._enable_mkldnn = enable_mkldnn
        self._write_lock = threading.Lock()
        self._engine_lock = threading.Lock()
        self._engine: Any = None
        self._stop = threading.Event()
        self._started_monotonic = time.monotonic()
        self._sequence = 0
        self._heartbeat_thread: threading.Thread | None = None

    def run(self) -> int:
        self._send(
            {
                "type": "worker.ready",
                "schemaVersion": SCHEMA_VERSION,
                "workerVersion": WORKER_VERSION,
                "startedAt": _utc_now(),
                "capabilities": self._capabilities(),
            }
        )

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="worker-heartbeat",
            daemon=True,
        )
        self._heartbeat_thread.start()

        try:
            for line in self._stdin:
                if self._handle_line(line):
                    break
        except KeyboardInterrupt:
            self._log("info", "interrupted")
        finally:
            self._stop.set()

        return 0

    def _capabilities(self) -> dict[str, Any]:
        core_ready = _module_available("numpy") and _module_available("cv2")
        fake_ready = self._ocr_mode == "fake" and self._ocr_lines_path is not None
        paddle_ready = self._ocr_mode == "paddle" and _module_available("paddleocr")
        recognition = core_ready and (fake_ready or paddle_ready)

        if not recognition:
            engine: str | None = None
        else:
            engine = "fake" if self._ocr_mode == "fake" else "paddleocr"

        return {
            "mode": "ocr" if recognition else "stub",
            "ocrEngine": engine,
            "recognition": recognition,
            "liveCapture": False,
        }

    def _handle_line(self, line: str) -> bool:
        """Handle one message and return True when the worker should stop."""

        stripped = line.strip()
        if not stripped:
            return False

        try:
            message: Any = json.loads(stripped)
        except json.JSONDecodeError as exc:
            self._send_error(
                "invalid_json",
                f"Could not parse message: {exc.msg}",
                detail=stripped[:500],
            )
            return False

        if not isinstance(message, dict):
            self._send_error("invalid_message", "Message must be a JSON object.")
            return False

        if message.get("schemaVersion") != SCHEMA_VERSION:
            self._send_error(
                "unsupported_schema_version",
                f"Expected schemaVersion {SCHEMA_VERSION}.",
                detail=repr(message.get("schemaVersion")),
            )
            return False

        message_type = message.get("type")
        request_id = message.get("requestId")
        correlated_request_id = request_id if isinstance(request_id, str) else None

        if message_type == "worker.ping":
            if not isinstance(request_id, str) or not request_id:
                self._send_error("invalid_message", "worker.ping requires a requestId.")
                return False

            self._send(
                {
                    "type": "worker.pong",
                    "schemaVersion": SCHEMA_VERSION,
                    "requestId": request_id,
                    "receivedAt": _utc_now(),
                }
            )
            return False

        if message_type == "worker.shutdown":
            reason = message.get("reason")
            self._send(
                {
                    "type": "worker.stopping",
                    "schemaVersion": SCHEMA_VERSION,
                    "reason": reason if isinstance(reason, str) else None,
                }
            )
            self._log("info", f"shutdown requested: {reason or 'no reason'}")
            return True

        if message_type == "recognition.analyze":
            self._handle_analyze(message, correlated_request_id)
            return False

        self._send_error(
            "unsupported_type",
            f"Unsupported message type: {message_type!r}",
            request_id=correlated_request_id,
        )
        return False

    def _handle_analyze(self, message: Mapping[str, Any], request_id: str | None) -> None:
        try:
            request = _parse_analyze_request(message)
        except ValueError as exc:
            self._send_error(
                "invalid_message",
                f"Invalid recognition.analyze request: {exc}",
                request_id=request_id,
            )
            return

        request_id = request["requestId"]

        try:
            # Imported here so the lifecycle-only worker stays free of the
            # recognition dependency tree. Imports and OCR execution stay on
            # the main thread; importing C extensions from a helper thread
            # while stdin blocks can deadlock on Windows.
            from .catalog import load_catalog
            from .geometry import NormalizedRect
            from .normalize import NormalizationConfig
            from .pipeline import PipelineConfig, recognize_path

            game_set = load_catalog(request["catalogPath"])
            expected_set = request.get("setId")
            if expected_set is not None and expected_set != game_set.id:
                raise ValueError(
                    f"requested set {expected_set!r} does not match catalog "
                    f"{game_set.id!r}"
                )

            rect = NormalizedRect.from_mapping(request["crop"])
            config = PipelineConfig(
                game_set=game_set,
                preprocess_mode=request.get("preprocessMode", DEFAULT_PREPROCESS_MODE),
                min_confidence=request.get("minConfidence", 0.6),
                min_ocr_confidence=request.get("minOcrConfidence", 0.5),
                normalization=NormalizationConfig(),
            )
            config.validate()

            run = recognize_path(
                request["imagePath"],
                rect,
                self._get_engine(),
                config,
            )
            # The request timestamp is authoritative; recognize_path defaults
            # to the file mtime when it is not supplied.
            result = replace(run.result, capture_timestamp=request["captureTimestamp"])
            payload = result.to_dict()
            payload["requestId"] = request_id
            self._send(payload)
        except Exception as exc:  # noqa: BLE001 - report instead of crashing the worker
            self._log("error", f"analysis {request_id} failed: {exc}")
            self._send_error(
                "analysis_failed",
                str(exc) or type(exc).__name__,
                detail=traceback.format_exc(limit=6),
                request_id=request_id,
            )

    def _get_engine(self) -> Any:
        with self._engine_lock:
            if self._engine is None:
                if self._ocr_mode == "fake":
                    if not self._ocr_lines_path:
                        raise ValueError("fake OCR mode requires --ocr-lines")
                    from .ocr.fake import FakeOcrEngine

                    self._engine = FakeOcrEngine.from_file(self._ocr_lines_path)
                else:
                    from .ocr.paddle import PaddleOcrEngine

                    self._engine = PaddleOcrEngine(
                        lang=self._lang,
                        model_dir=self._model_dir,
                        enable_mkldnn=self._enable_mkldnn,
                    )
            return self._engine

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_interval):
            self._sequence += 1
            self._send(
                {
                    "type": "worker.heartbeat",
                    "schemaVersion": SCHEMA_VERSION,
                    "sequence": self._sequence,
                    "sentAt": _utc_now(),
                    "uptimeMs": round((time.monotonic() - self._started_monotonic) * 1000),
                }
            )

    def _send(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=False)

        with self._write_lock:
            try:
                self._stdout.write(payload + "\n")
                self._stdout.flush()
            except (BrokenPipeError, OSError):
                self._stop.set()

    def _send_error(
        self,
        code: str,
        message: str,
        detail: str | None = None,
        request_id: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": "worker.error",
            "schemaVersion": SCHEMA_VERSION,
            "code": code,
            "message": message,
        }
        if detail is not None:
            payload["detail"] = detail
        if request_id is not None:
            payload["requestId"] = request_id
        self._send(payload)
        self._log("warn", f"{code}: {message}")

    def _log(self, level: str, message: str) -> None:
        try:
            self._stderr.write(
                json.dumps(
                    {"type": "worker.log", "level": level, "message": message},
                    ensure_ascii=False,
                )
                + "\n"
            )
            self._stderr.flush()
        except (BrokenPipeError, OSError):
            pass


def _parse_analyze_request(message: Mapping[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {
        "requestId": _required_str(message, "requestId"),
        "imagePath": _required_str(message, "imagePath"),
        "captureTimestamp": _required_str(message, "captureTimestamp"),
        "catalogPath": _required_str(message, "catalogPath"),
        "crop": _parse_crop(message.get("crop")),
    }

    for key in ("setId", "preprocessMode"):
        value = message.get(key)
        if value is not None:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{key} must be a non-empty string")
            request[key] = value

    for key in ("minConfidence", "minOcrConfidence"):
        value = message.get(key)
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            number = float(value)
            if not 0.0 <= number <= 1.0:
                raise ValueError(f"{key} must be between 0 and 1")
            request[key] = number

    return request


def _required_str(message: Mapping[str, Any], key: str) -> str:
    value = message.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _parse_crop(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("crop must be an object")

    crop: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        raw = value.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"crop.{key} must be a number")
        crop[key] = float(raw)

    for key in ("x", "y"):
        if crop[key] < 0 or crop[key] > 1:
            raise ValueError(f"crop.{key} must be between 0 and 1")
    for key in ("width", "height"):
        if crop[key] <= 0 or crop[key] > 1:
            raise ValueError(f"crop.{key} must be greater than 0 and at most 1")
    if crop["x"] + crop["width"] > 1 + 1e-9:
        raise ValueError("crop.x + crop.width must be at most 1")
    if crop["y"] + crop["height"] > 1 + 1e-9:
        raise ValueError("crop.y + crop.height must be at most 1")

    return crop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tft-recognition-worker",
        description="Stdio JSON-lines recognition worker.",
    )
    parser.add_argument(
        "--ocr",
        choices=("paddle", "fake"),
        default="paddle",
        help="OCR engine. 'fake' is for tests and requires --ocr-lines.",
    )
    parser.add_argument(
        "--ocr-lines",
        help="Fake OCR JSON lines file; only used with --ocr fake.",
    )
    parser.add_argument(
        "--lang",
        default="ru",
        help="PaddleOCR language model (default: ru).",
    )
    parser.add_argument(
        "--model-dir",
        help="PaddleOCR model/cache directory.",
    )
    parser.add_argument(
        "--paddle-enable-mkldnn",
        action="store_true",
        help="Opt back into PaddleX MKLDNN, which fails on some Windows builds.",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        help="Seconds between heartbeat messages (default: 2.0).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.ocr == "fake" and not args.ocr_lines:
        build_parser().error("--ocr fake requires --ocr-lines")

    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", newline="\n")

    server = WorkerServer(
        sys.stdin,
        sys.stdout,
        sys.stderr,
        heartbeat_interval=args.heartbeat_interval,
        ocr_mode=args.ocr,
        ocr_lines_path=args.ocr_lines,
        lang=args.lang,
        model_dir=args.model_dir,
        enable_mkldnn=args.paddle_enable_mkldnn,
    )
    return server.run()


if __name__ == "__main__":
    raise SystemExit(main())
