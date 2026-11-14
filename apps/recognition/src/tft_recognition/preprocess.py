"""Image loading and preprocessing for OCR."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class ImageLoadError(RuntimeError):
    """Raised when an image cannot be decoded."""


PREPROCESS_MODES = (
    "raw",
    "upscale2x",
    "upscale3x",
    "gray",
    "gray_clahe",
    "upscale2x_gray_clahe",
    "upscale3x_gray_clahe",
    "upscale3x_adaptive",
    "threshold",
)

# OCR engines report bounding boxes in the coordinate space of the image they
# receive. The pipeline divides those boxes by this scale so every downstream
# artifact stays in original crop coordinates.
PREPROCESS_SCALES = {
    "raw": 1.0,
    "upscale2x": 2.0,
    "upscale3x": 3.0,
    "gray": 1.0,
    "gray_clahe": 1.0,
    "upscale2x_gray_clahe": 2.0,
    "upscale3x_gray_clahe": 3.0,
    "upscale3x_adaptive": 3.0,
    "threshold": 1.0,
}


def load_image(path: str | Path) -> np.ndarray:
    """Load an image in a path-safe way on Windows.

    ``cv2.imread`` does not reliably handle non-ASCII paths on Windows, so
    read bytes and decode them instead.
    """

    image_path = Path(path)
    try:
        data = np.fromfile(str(image_path), dtype=np.uint8)
    except OSError as exc:
        raise ImageLoadError(f"could not read image {image_path}: {exc}") from exc
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ImageLoadError(f"could not decode image {image_path}")
    return image


def save_image(path: str | Path, image: np.ndarray) -> None:
    """Write an image in a path-safe way on Windows."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix or ".png"
    success, encoded = cv2.imencode(suffix, image)
    if not success:
        raise ImageLoadError(f"could not encode image for {output_path}")
    encoded.tofile(str(output_path))


def preprocess_scale(mode: str) -> float:
    """Return the pixel scale factor a preprocessing mode applies."""

    if mode not in PREPROCESS_SCALES:
        raise ValueError(
            f"unknown preprocessing mode {mode!r}; choose from {', '.join(PREPROCESS_MODES)}"
        )
    return PREPROCESS_SCALES[mode]


def preprocess(image: np.ndarray, mode: str = "raw") -> np.ndarray:
    if mode not in PREPROCESS_MODES:
        raise ValueError(
            f"unknown preprocessing mode {mode!r}; choose from {', '.join(PREPROCESS_MODES)}"
        )
    if image is None or not hasattr(image, "shape"):
        raise ValueError("image is not a valid array")

    if mode == "raw":
        return image.copy()

    if mode == "upscale2x":
        return _upscale(image, 2.0)

    if mode == "upscale3x":
        return _upscale(image, 3.0)

    if mode == "gray":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if mode == "gray_clahe":
        return _gray_clahe(image)

    if mode == "upscale2x_gray_clahe":
        return _gray_clahe(_upscale(image, 2.0))

    if mode == "upscale3x_gray_clahe":
        return _gray_clahe(_upscale(image, 3.0))

    if mode == "upscale3x_adaptive":
        return _adaptive_threshold(_upscale(image, 3.0))

    if mode == "threshold":
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresholded = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        return cv2.cvtColor(thresholded, cv2.COLOR_GRAY2BGR)

    raise AssertionError("unreachable")


def _upscale(image: np.ndarray, factor: float) -> np.ndarray:
    return cv2.resize(
        image,
        None,
        fx=factor,
        fy=factor,
        interpolation=cv2.INTER_CUBIC,
    )


def _adaptive_threshold(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresholded = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        10,
    )
    return cv2.cvtColor(thresholded, cv2.COLOR_GRAY2BGR)


def _gray_clahe(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
