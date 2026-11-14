"""Normalized crop geometry and validation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


class CropValidationError(ValueError):
    """Raised when a normalized crop rectangle is invalid."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CropValidationError(f"{field} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise CropValidationError(f"{field} must be finite, got {value!r}")
    return number


@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int

    def to_list(self) -> list[int]:
        return [self.x, self.y, self.width, self.height]


@dataclass(frozen=True)
class NormalizedRect:
    """Crop rectangle expressed as fractions of the source dimensions."""

    x: float
    y: float
    width: float
    height: float

    def validate(self) -> None:
        values = {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }
        for field, value in values.items():
            if not math.isfinite(value):
                raise CropValidationError(f"crop.{field} must be finite")
        if self.x < 0 or self.y < 0:
            raise CropValidationError("crop.x and crop.y must be >= 0")
        if self.width <= 0 or self.height <= 0:
            raise CropValidationError("crop.width and crop.height must be > 0")
        tolerance = 1e-9
        if self.x + self.width > 1 + tolerance:
            raise CropValidationError("crop.x + crop.width must be <= 1")
        if self.y + self.height > 1 + tolerance:
            raise CropValidationError("crop.y + crop.height must be <= 1")

    def to_pixels(
        self,
        source_width: int,
        source_height: int,
        min_pixels: int = 32,
    ) -> PixelRect:
        self.validate()
        if source_width <= 0 or source_height <= 0:
            raise CropValidationError(
                f"source dimensions must be positive, got {source_width}x{source_height}"
            )

        x0 = int(round(self.x * source_width))
        y0 = int(round(self.y * source_height))
        x1 = int(round((self.x + self.width) * source_width))
        y1 = int(round((self.y + self.height) * source_height))

        x0 = max(0, min(x0, source_width))
        y0 = max(0, min(y0, source_height))
        x1 = max(0, min(x1, source_width))
        y1 = max(0, min(y1, source_height))

        pixel_width = x1 - x0
        pixel_height = y1 - y0
        if pixel_width < min_pixels or pixel_height < min_pixels:
            raise CropValidationError(
                "crop is too small: "
                f"{pixel_width}x{pixel_height}px, minimum is {min_pixels}px per side"
            )

        return PixelRect(x0, y0, pixel_width, pixel_height)

    def to_mapping(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        where: str = "crop",
    ) -> "NormalizedRect":
        if not isinstance(value, Mapping):
            raise CropValidationError(f"{where} must be an object")
        missing = [key for key in ("x", "y", "width", "height") if key not in value]
        if missing:
            raise CropValidationError(f"{where} is missing: {', '.join(missing)}")
        rect = cls(
            x=_finite_number(value["x"], f"{where}.x"),
            y=_finite_number(value["y"], f"{where}.y"),
            width=_finite_number(value["width"], f"{where}.width"),
            height=_finite_number(value["height"], f"{where}.height"),
        )
        rect.validate()
        return rect

    @classmethod
    def from_string(cls, value: str, *, where: str = "--crop") -> "NormalizedRect":
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 4:
            raise CropValidationError(
                f"{where} must have four comma-separated values: x,y,width,height"
            )
        try:
            numbers = [float(part) for part in parts]
        except ValueError as exc:
            raise CropValidationError(f"{where} contains a non-numeric value") from exc
        rect = cls(*numbers)
        rect.validate()
        return rect


def crop_image(image: np.ndarray, rect: NormalizedRect, *, min_pixels: int = 32) -> tuple[np.ndarray, PixelRect]:
    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        raise CropValidationError("image is not a valid array")
    height, width = image.shape[:2]
    pixels = rect.to_pixels(width, height, min_pixels=min_pixels)
    cropped = image[
        pixels.y : pixels.y + pixels.height,
        pixels.x : pixels.x + pixels.width,
    ].copy()
    if cropped.size == 0:
        raise CropValidationError("crop produced an empty image")
    return cropped, pixels
