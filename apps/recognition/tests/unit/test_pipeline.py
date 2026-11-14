from __future__ import annotations

import numpy as np
import pytest

from tft_recognition.geometry import CropValidationError, NormalizedRect
from tft_recognition.ocr.base import OcrLine
from tft_recognition.ocr.fake import FakeOcrEngine
from tft_recognition.pipeline import PipelineConfig, recognize_image
from tft_recognition.result import compare_expected


def line(
    text: str,
    left: float,
    top: float,
    width: float = 120,
    height: float = 20,
    confidence: float = 0.95,
) -> OcrLine:
    return OcrLine(
        text=text,
        confidence=confidence,
        box=(left, top, left + width, top + height),
    )


def run(lines, catalog):
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    return recognize_image(
        image,
        NormalizedRect(0.0, 0.0, 1.0, 1.0),
        FakeOcrEngine(lines),
        PipelineConfig(game_set=catalog),
    )


def test_ok_result(catalog) -> None:
    run_result = run(
        [
            line("2", left=10, top=20, width=20),
            line("Инферно", left=45, top=20, width=150),
        ],
        catalog,
    )
    assert run_result.result.status == "ok"
    assert len(run_result.result.traits) == 1
    trait = run_result.result.traits[0]
    assert trait.trait_id == "Inferno"
    assert trait.count == 2
    assert run_result.result.unknown_rows == ()


def test_unknown_row_makes_result_partial(catalog) -> None:
    run_result = run(
        [
            line("2", left=10, top=20, width=20),
            line("Неизвестный", left=45, top=20, width=150),
        ],
        catalog,
    )
    assert run_result.result.status == "partial"
    assert run_result.result.traits == ()
    assert run_result.result.unknown_rows[0].reason == "no_catalog_match"


def test_missing_count_is_an_unknown_row(catalog) -> None:
    run_result = run([line("Фея", left=45, top=20, width=80)], catalog)
    assert run_result.result.status == "partial"
    assert run_result.result.unknown_rows[0].reason == "missing_count"


def test_empty_ocr_is_unavailable(catalog) -> None:
    run_result = run([], catalog)
    assert run_result.result.status == "unavailable"


def test_low_confidence_is_kept_visible(catalog) -> None:
    run_result = run(
        [
            line("2", left=10, top=20, width=20, confidence=0.5),
            line("Инферно", left=45, top=20, width=150, confidence=0.5),
        ],
        catalog,
    )
    assert run_result.result.status == "partial"
    assert len(run_result.result.traits) == 1
    assert run_result.result.traits[0].confidence == 0.5
    assert any("low_confidence" in warning for warning in run_result.result.diagnostics["warnings"])


def test_very_low_confidence_is_dropped_before_parsing(catalog) -> None:
    run_result = run(
        [
            line("2", left=10, top=20, width=20, confidence=0.2),
            line("Инферно", left=45, top=20, width=150, confidence=0.3),
        ],
        catalog,
    )
    assert run_result.result.status == "unavailable"
    assert run_result.result.traits == ()
    assert {
        ignored["reason"] for ignored in run_result.result.diagnostics["ignoredLines"]
    } == {"low_ocr_confidence"}


def test_duplicate_trait_is_preserved_as_unknown(catalog) -> None:
    run_result = run(
        [
            line("2", left=10, top=20, width=20),
            line("Инферно", left=45, top=20, width=150),
            line("1", left=10, top=80, width=20),
            line("Инферно", left=45, top=80, width=150),
        ],
        catalog,
    )
    assert run_result.result.status == "partial"
    assert len(run_result.result.traits) == 1
    assert run_result.result.unknown_rows[0].reason == "duplicate_trait"


def test_ocr_error_returns_error_status(catalog) -> None:
    class FailingEngine:
        name = "failing"

        def recognize(self, image):
            raise RuntimeError("boom")

    run_result = recognize_image(
        np.zeros((200, 200, 3), dtype=np.uint8),
        NormalizedRect(0.0, 0.0, 1.0, 1.0),
        FailingEngine(),
        PipelineConfig(game_set=catalog),
    )
    assert run_result.result.status == "error"
    assert "boom" in run_result.result.diagnostics["error"]


def test_invalid_crop_raises(catalog) -> None:
    with pytest.raises(CropValidationError):
        recognize_image(
            np.zeros((200, 200, 3), dtype=np.uint8),
            NormalizedRect(1.0, 0.0, 1.0, 1.0),
            FakeOcrEngine([]),
            PipelineConfig(game_set=catalog),
        )


def test_compare_expected(catalog) -> None:
    run_result = run(
        [
            line("2", left=10, top=20, width=20),
            line("Инферно", left=45, top=20, width=150),
        ],
        catalog,
    )
    assert compare_expected(run_result.result, {"Инферно": 2})["passed"] is True
    assert compare_expected(run_result.result, {"Инферно": 1})["passed"] is False
