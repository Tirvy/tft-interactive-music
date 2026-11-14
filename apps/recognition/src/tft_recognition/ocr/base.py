"""OCR adapter contract.

The rest of the recognition pipeline depends only on this module, never on a
specific OCR library.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

import numpy as np


class OcrEngineError(RuntimeError):
    """Raised when an OCR engine is unavailable or recognition fails."""


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    # Axis-aligned bounding box: left, top, right, bottom.
    box: tuple[float, float, float, float]


@runtime_checkable
class OcrEngine(Protocol):
    name: str

    def recognize(self, image: np.ndarray) -> Sequence[OcrLine]:
        """Return recognized lines in the engine's natural order."""
