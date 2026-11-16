"""Lifecycle and analysis tests for the stdio worker.

These tests launch the real module in a subprocess because the worker's
contract is its stdin/stdout behavior, not an in-process API.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, TextIO

import pytest

RECOGNITION_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = RECOGNITION_DIR.parents[1]
SRC_DIR = RECOGNITION_DIR / "src"
DEMO_LINES = RECOGNITION_DIR / "tests" / "fixtures" / "ocr" / "demo-lines.json"
CATALOG = (
    RECOGNITION_DIR / "tests" / "fixtures" / "catalog" / "set-18-ru.fixture.json"
)
SCREENSHOT = REPO_ROOT / "tests" / "ru" / "screenshot-1.png"

POC_CROP = {"x": 0.0, "y": 0.2, "width": 0.16, "height": 0.5}


def start_worker(*extra_args: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(SRC_DIR) + os.pathsep + python_path if python_path else str(SRC_DIR)
    )
    env["PYTHONIOENCODING"] = "utf-8"

    # The fake engine keeps lifecycle and protocol tests independent of
    # PaddleOCR while still exercising the real pipeline.
    args = [
        sys.executable,
        "-m",
        "tft_recognition.worker",
        "--ocr",
        "fake",
        "--ocr-lines",
        str(DEMO_LINES),
        *extra_args,
    ]

    return subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        cwd=str(RECOGNITION_DIR),
        env=env,
    )


def send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def read_until(stream: TextIO, expected_type: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    seen: list[str] = []

    while time.monotonic() < deadline:
        line = stream.readline()
        if line == "":
            pytest.fail(f"worker closed stdout while waiting for {expected_type}")
        message = json.loads(line)
        seen.append(str(message.get("type")))
        if message.get("type") == expected_type:
            return message

    pytest.fail(f"timed out waiting for {expected_type}; saw {seen}")


def stop_worker(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    send(
        process,
        {
            "type": "worker.shutdown",
            "schemaVersion": 1,
            "reason": "pytest",
        },
    )

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_worker_announces_ready_answers_ping_and_shuts_down() -> None:
    process = start_worker("--heartbeat-interval", "0.1")

    try:
        assert process.stdout is not None
        ready = read_until(process.stdout, "worker.ready")

        assert ready["schemaVersion"] == 1
        assert ready["workerVersion"] == "0.2.0"
        assert ready["capabilities"] == {
            "mode": "ocr",
            "ocrEngine": "fake",
            "recognition": True,
            "liveCapture": False,
        }

        send(
            process,
            {
                "type": "worker.ping",
                "schemaVersion": 1,
                "requestId": "req-1",
                "sentAt": "2026-11-15T10:00:00.000Z",
            },
        )
        pong = read_until(process.stdout, "worker.pong")
        assert pong["requestId"] == "req-1"
        assert pong["receivedAt"]

        send(
            process,
            {
                "type": "worker.shutdown",
                "schemaVersion": 1,
                "reason": "pytest",
            },
        )
        stopping = read_until(process.stdout, "worker.stopping")
        assert stopping["reason"] == "pytest"
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_worker_reports_protocol_errors_without_exiting() -> None:
    process = start_worker("--heartbeat-interval", "0.1")

    try:
        assert process.stdin is not None
        assert process.stdout is not None

        read_until(process.stdout, "worker.ready")

        process.stdin.write("this is not json\n")
        process.stdin.flush()
        invalid_json = read_until(process.stdout, "worker.error")
        assert invalid_json["code"] == "invalid_json"

        send(
            process,
            {
                "type": "worker.ping",
                "schemaVersion": 99,
                "requestId": "req-bad-version",
                "sentAt": "2026-11-15T10:00:00.000Z",
            },
        )
        bad_version = read_until(process.stdout, "worker.error")
        assert bad_version["code"] == "unsupported_schema_version"

        send(
            process,
            {
                "type": "worker.unknown",
                "schemaVersion": 1,
            },
        )
        unsupported = read_until(process.stdout, "worker.error")
        assert unsupported["code"] == "unsupported_type"

        send(
            process,
            {
                "type": "worker.ping",
                "schemaVersion": 1,
                "requestId": "req-after-errors",
                "sentAt": "2026-11-15T10:00:00.000Z",
            },
        )
        pong = read_until(process.stdout, "worker.pong")
        assert pong["requestId"] == "req-after-errors"
    finally:
        stop_worker(process)


def test_worker_analyzes_an_image_with_fake_ocr() -> None:
    process = start_worker("--heartbeat-interval", "0.5")

    try:
        assert process.stdout is not None
        read_until(process.stdout, "worker.ready")

        send(
            process,
            {
                "type": "recognition.analyze",
                "schemaVersion": 1,
                "requestId": "req-analyze",
                "imagePath": str(SCREENSHOT),
                "captureTimestamp": "2026-11-15T10:00:00.000Z",
                "crop": POC_CROP,
                "catalogPath": str(CATALOG),
                "preprocessMode": "raw",
            },
        )

        result = read_until(process.stdout, "recognition.result", timeout=30)
        assert result["requestId"] == "req-analyze"
        assert result["captureTimestamp"] == "2026-11-15T10:00:00.000Z"
        assert result["setId"] == "set-18"
        assert result["status"] == "ok"
        assert result["unknownRows"] == []
        traits = {trait["displayName"]: trait["count"] for trait in result["traits"]}
        assert traits == {"Инферно": 2, "Фея": 1}
        assert result["diagnostics"]["sourceSize"] == [1912, 1205]
        assert result["diagnostics"]["ocrEngine"] == "fake"
    finally:
        stop_worker(process)


def test_worker_rejects_invalid_analyze_requests() -> None:
    process = start_worker("--heartbeat-interval", "0.5")

    try:
        assert process.stdout is not None
        read_until(process.stdout, "worker.ready")

        send(
            process,
            {
                "type": "recognition.analyze",
                "schemaVersion": 1,
                "requestId": "req-invalid",
                "imagePath": "",
                "captureTimestamp": "2026-11-15T10:00:00.000Z",
                "crop": POC_CROP,
                "catalogPath": str(CATALOG),
            },
        )
        error = read_until(process.stdout, "worker.error")
        assert error["code"] == "invalid_message"
        assert error["requestId"] == "req-invalid"

        send(
            process,
            {
                "type": "recognition.analyze",
                "schemaVersion": 1,
                "requestId": "req-missing-image",
                "imagePath": str(RECOGNITION_DIR / "does-not-exist.png"),
                "captureTimestamp": "2026-11-15T10:00:00.000Z",
                "crop": POC_CROP,
                "catalogPath": str(CATALOG),
                "preprocessMode": "raw",
            },
        )
        failure = read_until(process.stdout, "worker.error", timeout=30)
        assert failure["code"] == "analysis_failed"
        assert failure["requestId"] == "req-missing-image"

        send(
            process,
            {
                "type": "worker.ping",
                "schemaVersion": 1,
                "requestId": "req-still-alive",
                "sentAt": "2026-11-15T10:00:00.000Z",
            },
        )
        pong = read_until(process.stdout, "worker.pong")
        assert pong["requestId"] == "req-still-alive"
    finally:
        stop_worker(process)
