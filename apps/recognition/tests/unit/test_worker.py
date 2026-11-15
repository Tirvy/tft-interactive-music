"""Lifecycle tests for the stdio worker stub.

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
SRC_DIR = RECOGNITION_DIR / "src"


def start_worker(*extra_args: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(SRC_DIR) + os.pathsep + python_path if python_path else str(SRC_DIR)
    )
    env["PYTHONIOENCODING"] = "utf-8"

    return subprocess.Popen(
        [sys.executable, "-m", "tft_recognition.worker", *extra_args],
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


def read_until(stream: TextIO, expected_type: str, timeout: float = 5.0) -> dict[str, Any]:
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
        assert ready["workerVersion"] == "0.1.0"
        assert ready["capabilities"] == {
            "mode": "stub",
            "ocrEngine": None,
            "recognition": False,
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
