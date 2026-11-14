from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tft_recognition.cli import main
from tft_recognition.preprocess import save_image

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


def test_cli_with_fake_ocr(tmp_path, capsys) -> None:
    image_path = tmp_path / "synthetic.png"
    save_image(image_path, np.zeros((200, 200, 3), dtype=np.uint8))
    expected_path = tmp_path / "expected.json"
    expected_path.write_text(
        json.dumps(
            {
                "traits": {"Инферно": 2, "Фея": 1},
                "progress": {"stage": 3, "round": 1},
                "players": [{"health": 15}, {"health": 4}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--image",
            str(image_path),
            "--crop",
            "0,0,1,1",
            "--catalog",
            str(FIXTURE_ROOT / "catalog" / "set-18-ru.fixture.json"),
            "--ocr",
            "fake",
            "--ocr-lines",
            str(FIXTURE_ROOT / "ocr" / "demo-lines.json"),
            "--expected",
            str(expected_path),
            "--fail-on-mismatch",
            "--pretty",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert len(payload["traits"]) == 2
    assert payload["diagnostics"]["expectedComparison"]["passed"] is True


def test_cli_invalid_crop_returns_usage_error(tmp_path, capsys) -> None:
    image_path = tmp_path / "synthetic.png"
    save_image(image_path, np.zeros((200, 200, 3), dtype=np.uint8))
    exit_code = main(
        [
            "--image",
            str(image_path),
            "--crop",
            "0.9,0,0.5,0.5",
            "--catalog",
            str(FIXTURE_ROOT / "catalog" / "set-18-ru.fixture.json"),
            "--ocr",
            "fake",
            "--ocr-lines",
            str(FIXTURE_ROOT / "ocr" / "demo-lines.json"),
        ]
    )
    assert exit_code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_fake_requires_lines(tmp_path, capsys) -> None:
    image_path = tmp_path / "synthetic.png"
    save_image(image_path, np.zeros((200, 200, 3), dtype=np.uint8))
    exit_code = main(
        [
            "--image",
            str(image_path),
            "--crop",
            "0,0,1,1",
            "--catalog",
            str(FIXTURE_ROOT / "catalog" / "set-18-ru.fixture.json"),
            "--ocr",
            "fake",
        ]
    )
    assert exit_code == 2
    assert "requires --ocr-lines" in capsys.readouterr().err
