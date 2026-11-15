"""Stdio JSON-lines worker entry point.

This is the Milestone 1 lifecycle stub: it announces readiness, emits
heartbeats, answers pings, and shuts down cleanly. It deliberately does not
import OpenCV, PaddleOCR, or any other recognition dependency, so the desktop
app can manage the process quickly before the OCR milestone begins.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Sequence, TextIO

SCHEMA_VERSION = 1
WORKER_VERSION = "0.1.0"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 2.0


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class WorkerServer:
    """A single-process, single-connection JSON-lines server."""

    def __init__(
        self,
        stdin: TextIO,
        stdout: TextIO,
        stderr: TextIO,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        mode: str = "stub",
    ) -> None:
        self._stdin = stdin
        self._stdout = stdout
        self._stderr = stderr
        self._heartbeat_interval = max(0.01, heartbeat_interval)
        self._mode = mode
        self._write_lock = threading.Lock()
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
                "capabilities": {
                    "mode": self._mode,
                    "ocrEngine": None,
                    "recognition": False,
                    "liveCapture": False,
                },
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

        if message_type == "worker.ping":
            request_id = message.get("requestId")
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

        self._send_error(
            "unsupported_type",
            f"Unsupported message type: {message_type!r}",
        )
        return False

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

    def _send_error(self, code: str, message: str, detail: str | None = None) -> None:
        payload: dict[str, Any] = {
            "type": "worker.error",
            "schemaVersion": SCHEMA_VERSION,
            "code": code,
            "message": message,
        }
        if detail is not None:
            payload["detail"] = detail
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tft-recognition-worker",
        description="Stdio JSON-lines recognition worker (lifecycle stub).",
    )
    parser.add_argument(
        "--mode",
        choices=("stub",),
        default="stub",
        help="Worker mode. Only the lifecycle stub exists in Milestone 1.",
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
        mode=args.mode,
    )
    return server.run()


if __name__ == "__main__":
    raise SystemExit(main())
