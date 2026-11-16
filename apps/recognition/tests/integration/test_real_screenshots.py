from __future__ import annotations

import json
from pathlib import Path

import pytest

from tft_recognition.catalog import load_catalog
from tft_recognition.fixture import load_fixture
from tft_recognition.ocr.paddle import PaddleOcrEngine
from tft_recognition.pipeline import PipelineConfig, recognize_path
from tft_recognition.result import compare_expected, expected_traits

SCREENSHOT_ROOT = Path(__file__).resolve().parents[4] / "tests" / "ru"


@pytest.mark.ocr
@pytest.mark.parametrize("name", ["screenshot-1", "screenshot-2", "screenshot-3"])
def test_real_screenshot_matches_expected(name: str) -> None:
    pytest.importorskip("paddleocr")
    manifest = load_fixture(SCREENSHOT_ROOT / f"{name}.fixture.json")
    catalog = load_catalog(manifest.catalog)
    expected = expected_traits(
        json.loads(manifest.expected_file.read_text(encoding="utf-8"))
    )

    engine = PaddleOcrEngine(lang="ru")
    run = recognize_path(
        manifest.image,
        manifest.crop,
        engine,
        PipelineConfig(game_set=catalog, preprocess_mode="upscale3x_adaptive"),
    )

    assert run.result.status != "error", run.result.diagnostics
    comparison = compare_expected(run.result, expected)
    assert comparison["passed"], comparison
    assert run.result.status == "ok", run.result.diagnostics
