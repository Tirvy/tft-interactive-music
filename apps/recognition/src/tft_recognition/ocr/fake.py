"""Deterministic OCR adapter used by unit tests and pipeline development."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .base import OcrLine


class FakeOcrEngine:
    name = "fake"

    def __init__(self, lines: Sequence[OcrLine], *, name: str = "fake") -> None:
        self._lines = tuple(lines)
        self.name = name

    def recognize(self, image: np.ndarray) -> Sequence[OcrLine]:
        return self._lines

    @classmethod
    def from_file(cls, path: str | Path) -> "FakeOcrEngine":
        lines = load_fake_lines(path)
        return cls(lines)


def load_fake_lines(path: str | Path) -> list[OcrLine]:
    data: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "lines" not in data:
            raise ValueError("fake OCR JSON object must contain a 'lines' array")
        data = data["lines"]
    if not isinstance(data, list):
        raise ValueError("fake OCR JSON must be an array or an object with 'lines'")

    lines: list[OcrLine] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"fake OCR line {index} must be an object")
        text = item.get("text")
        confidence = item.get("confidence", 1.0)
        box = item.get("box")
        if not isinstance(text, str):
            raise ValueError(f"fake OCR line {index}.text must be a string")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ValueError(f"fake OCR line {index}.confidence must be a number")
        if (
            not isinstance(box, list)
            or len(box) != 4
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in box)
        ):
            raise ValueError(
                f"fake OCR line {index}.box must be [left, top, right, bottom]"
            )
        lines.append(
            OcrLine(
                text=text,
                confidence=float(confidence),
                box=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
            )
        )
    return lines
