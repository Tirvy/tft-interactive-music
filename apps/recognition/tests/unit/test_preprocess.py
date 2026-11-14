from __future__ import annotations

import numpy as np
import pytest

from tft_recognition.preprocess import PREPROCESS_MODES, preprocess, preprocess_scale


def test_scales_match_upscaling_modes() -> None:
    assert preprocess_scale("raw") == 1.0
    assert preprocess_scale("upscale2x") == 2.0
    assert preprocess_scale("upscale3x_gray_clahe") == 3.0
    assert preprocess_scale("upscale3x_adaptive") == 3.0


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown preprocessing mode"):
        preprocess_scale("not-a-mode")
    with pytest.raises(ValueError, match="unknown preprocessing mode"):
        preprocess(np.zeros((10, 10, 3), dtype=np.uint8), "not-a-mode")


@pytest.mark.parametrize("mode", PREPROCESS_MODES)
def test_every_mode_returns_a_bgr_image(mode: str) -> None:
    image = np.zeros((20, 30, 3), dtype=np.uint8)
    processed = preprocess(image, mode)
    assert processed.ndim == 3
    assert processed.shape[2] == 3

    scale = int(preprocess_scale(mode))
    assert processed.shape[0] == image.shape[0] * scale
    assert processed.shape[1] == image.shape[1] * scale
