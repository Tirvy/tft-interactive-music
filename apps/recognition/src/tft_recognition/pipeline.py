"""Recognition pipeline orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .catalog import GameSet
from .geometry import NormalizedRect, PixelRect, crop_image
from .normalize import NormalizationConfig, resolve_label
from .ocr.base import OcrEngine, OcrLine
from .parse import IgnoredLine, ParseResult, parse_ocr_lines
from .preprocess import load_image, preprocess, preprocess_scale
from .result import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_UNAVAILABLE,
    RecognitionResult,
    TraitResult,
    UnknownRowResult,
    ignored_lines_to_dicts,
)


@dataclass(frozen=True)
class PipelineConfig:
    game_set: GameSet
    preprocess_mode: str = "upscale3x_adaptive"
    min_confidence: float = 0.6
    # Hard floor for OCR lines. Lines below this are discarded before parsing
    # and recorded as diagnostics instead of becoming phantom trait rows.
    min_ocr_confidence: float = 0.5
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)

    def validate(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if not 0.0 <= self.min_ocr_confidence <= 1.0:
            raise ValueError("min_ocr_confidence must be between 0 and 1")
        preprocess_scale(self.preprocess_mode)


@dataclass(frozen=True)
class RecognitionRun:
    result: RecognitionResult
    pixels: PixelRect
    cropped_image: np.ndarray
    processed_image: np.ndarray
    parsed: ParseResult

    def debug_artifacts(self) -> dict[str, np.ndarray]:
        return {
            "crop.png": self.cropped_image,
            "preprocessed.png": self.processed_image,
        }


def recognize_image(
    image: np.ndarray,
    rect: NormalizedRect,
    engine: OcrEngine,
    config: PipelineConfig,
    *,
    capture_timestamp: str | None = None,
    source_name: str | None = None,
) -> RecognitionRun:
    started = time.perf_counter()
    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        raise ValueError("image is not a valid array")
    config.validate()

    cropped, pixels = crop_image(image, rect)
    processed = preprocess(cropped, config.preprocess_mode)
    scale = preprocess_scale(config.preprocess_mode)
    source_height, source_width = image.shape[:2]
    timestamp = capture_timestamp or _now_iso()

    diagnostics: dict[str, Any] = {
        "ocrEngine": getattr(engine, "name", type(engine).__name__),
        "ocrModel": getattr(engine, "model_name", None),
        "sourceSize": [int(source_width), int(source_height)],
        "cropPx": pixels.to_list(),
        "cropNormalized": rect.to_mapping(),
        "cropValid": True,
        "preprocess": config.preprocess_mode,
        "ocrScale": scale,
        "minOcrConfidence": config.min_ocr_confidence,
        "setId": config.game_set.id,
        "catalogVersion": config.game_set.data_version,
        "locale": config.game_set.locale,
        "processedAt": _now_iso(),
        "warnings": [],
    }
    if source_name:
        diagnostics["sourceName"] = source_name

    try:
        ocr_lines = list(engine.recognize(processed))
    except Exception as exc:
        diagnostics["error"] = str(exc)
        diagnostics["elapsedMs"] = round((time.perf_counter() - started) * 1000, 3)
        return RecognitionRun(
            result=RecognitionResult(
                capture_timestamp=timestamp,
                set_id=config.game_set.id,
                status=STATUS_ERROR,
                diagnostics=diagnostics,
            ),
            pixels=pixels,
            cropped_image=cropped,
            processed_image=processed,
            parsed=ParseResult(rows=(), ignored_lines=()),
        )

    scaled_lines: list[OcrLine] = []
    dropped_lines: list[IgnoredLine] = []
    for ocr_line in ocr_lines:
        scaled = _scale_ocr_line(ocr_line, scale)
        if (
            scaled.confidence is not None
            and scaled.confidence < config.min_ocr_confidence
        ):
            dropped_lines.append(
                IgnoredLine(
                    text=scaled.text,
                    reason="low_ocr_confidence",
                    confidence=scaled.confidence,
                    box=scaled.box,
                )
            )
            continue
        scaled_lines.append(scaled)

    parsed = parse_ocr_lines(scaled_lines)
    if dropped_lines:
        parsed = ParseResult(
            rows=parsed.rows,
            ignored_lines=(*dropped_lines, *parsed.ignored_lines),
        )
    diagnostics["ocrLineCount"] = len(ocr_lines)
    diagnostics["retainedOcrLineCount"] = len(scaled_lines)
    traits: list[TraitResult] = []
    unknown_rows: list[UnknownRowResult] = []
    seen_trait_ids: set[str] = set()
    low_confidence = False

    for row in parsed.rows:
        count = _parse_count(row.count_text)
        if row.label_text is None:
            unknown_rows.append(
                UnknownRowResult(
                    raw_text=row.raw_text,
                    count=count,
                    reason="missing_label",
                    confidence=row.confidence,
                    bbox=row.bbox,
                )
            )
            continue
        if row.count_text is None or count is None:
            unknown_rows.append(
                UnknownRowResult(
                    raw_text=row.raw_text,
                    count=None,
                    reason="missing_count",
                    confidence=row.confidence,
                    bbox=row.bbox,
                )
            )
            continue

        match = resolve_label(row.label_text, config.game_set, config.normalization)
        if match.trait is None:
            unknown_rows.append(
                UnknownRowResult(
                    raw_text=row.raw_text,
                    count=count,
                    reason=match.reason or "no_catalog_match",
                    confidence=row.confidence,
                    bbox=row.bbox,
                    candidate_id=match.best_candidate_id,
                    candidate_display_name=match.best_candidate_display_name,
                )
            )
            continue

        if match.trait.id in seen_trait_ids:
            unknown_rows.append(
                UnknownRowResult(
                    raw_text=row.raw_text,
                    count=count,
                    reason="duplicate_trait",
                    confidence=row.confidence,
                    bbox=row.bbox,
                    candidate_id=match.trait.id,
                    candidate_display_name=match.trait.display_name,
                )
            )
            continue
        seen_trait_ids.add(match.trait.id)

        if row.confidence is None:
            diagnostics["warnings"].append(f"missing_confidence:{match.trait.id}")
            low_confidence = True
        elif row.confidence < config.min_confidence:
            diagnostics["warnings"].append(
                f"low_confidence:{match.trait.id}:{row.confidence:.3f}"
            )
            low_confidence = True

        traits.append(
            TraitResult(
                trait_id=match.trait.id,
                display_name=match.trait.display_name,
                raw_text=row.raw_text,
                count=count,
                confidence=row.confidence,
                match_method=match.method,
                match_score=match.score,
                match_margin=match.margin,
            )
        )

    if not parsed.rows:
        status = STATUS_UNAVAILABLE
    elif unknown_rows or low_confidence:
        status = STATUS_PARTIAL
    else:
        status = STATUS_OK

    diagnostics.update(
        {
            "rowCount": len(parsed.rows),
            "traitCount": len(traits),
            "unknownCount": len(unknown_rows),
            "ignoredLines": ignored_lines_to_dicts(parsed.ignored_lines),
            "elapsedMs": round((time.perf_counter() - started) * 1000, 3),
        }
    )

    return RecognitionRun(
        result=RecognitionResult(
            capture_timestamp=timestamp,
            set_id=config.game_set.id,
            status=status,
            traits=tuple(traits),
            unknown_rows=tuple(unknown_rows),
            diagnostics=diagnostics,
        ),
        pixels=pixels,
        cropped_image=cropped,
        processed_image=processed,
        parsed=parsed,
    )


def recognize_path(
    image_path: str | Path,
    rect: NormalizedRect,
    engine: OcrEngine,
    config: PipelineConfig,
) -> RecognitionRun:
    path = Path(image_path)
    image = load_image(path)
    try:
        modified = path.stat().st_mtime
        capture_timestamp = datetime.fromtimestamp(
            modified, tz=timezone.utc
        ).isoformat().replace("+00:00", "Z")
    except OSError:
        capture_timestamp = _now_iso()
    return recognize_image(
        image,
        rect,
        engine,
        config,
        capture_timestamp=capture_timestamp,
        source_name=path.name,
    )


def _scale_ocr_line(line: OcrLine, scale: float) -> OcrLine:
    """Map OCR boxes back to original crop coordinates."""

    if scale == 1.0:
        return line
    box = line.box
    return OcrLine(
        text=line.text,
        confidence=line.confidence,
        box=(box[0] / scale, box[1] / scale, box[2] / scale, box[3] / scale),
    )


def _parse_count(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
