from __future__ import annotations

import numpy as np
import pytest

from tft_recognition.geometry import (
    CropValidationError,
    NormalizedRect,
    PixelRect,
    crop_image,
)


def test_valid_rect_converts_to_pixels() -> None:
    rect = NormalizedRect(x=0.1, y=0.2, width=0.3, height=0.4)
    assert rect.to_pixels(1000, 500) == PixelRect(100, 100, 300, 200)


@pytest.mark.parametrize(
    "rect",
    [
        NormalizedRect(-0.1, 0.0, 0.5, 0.5),
        NormalizedRect(0.0, -0.1, 0.5, 0.5),
        NormalizedRect(0.0, 0.0, 0.0, 0.5),
        NormalizedRect(0.0, 0.0, 0.5, 0.0),
        NormalizedRect(0.8, 0.0, 0.3, 0.5),
        NormalizedRect(0.0, 0.8, 0.5, 0.3),
        NormalizedRect(float("nan"), 0.0, 0.5, 0.5),
        NormalizedRect(0.0, float("inf"), 0.5, 0.5),
    ],
)
def test_invalid_rects_are_rejected(rect: NormalizedRect) -> None:
    with pytest.raises(CropValidationError):
        rect.validate()


def test_too_small_crop_is_rejected() -> None:
    rect = NormalizedRect(0.0, 0.0, 0.01, 0.01)
    with pytest.raises(CropValidationError, match="too small"):
        rect.to_pixels(100, 100)


def test_from_mapping_requires_all_fields() -> None:
    with pytest.raises(CropValidationError, match="missing"):
        NormalizedRect.from_mapping({"x": 0.0, "y": 0.0, "width": 0.5})


def test_from_string_parses_normalized_values() -> None:
    assert NormalizedRect.from_string("0,0.2,0.16,0.5") == NormalizedRect(
        0.0, 0.2, 0.16, 0.5
    )


def test_crop_image_returns_expected_shape() -> None:
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    cropped, pixels = crop_image(image, NormalizedRect(0.5, 0.5, 0.5, 0.5))
    assert pixels == PixelRect(100, 50, 100, 50)
    assert cropped.shape == (50, 100, 3)
