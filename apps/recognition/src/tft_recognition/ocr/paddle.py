"""PaddleOCR adapter.

PaddleOCR is imported lazily so that the parsing, normalization, and pipeline
tests can run without the optional OCR dependency installed.
"""

from __future__ import annotations

import json as jsonlib
import os
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .base import OcrEngineError, OcrLine

_MKLDNN_ENV = "PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"
# PaddlePaddle 3.3 on Windows fails inside oneDNN with
# "ConvertPirAttribute2RuntimeAttribute not support
# [pir::ArrayAttribute<pir::DoubleAttribute>]". PaddleX reads this flag when
# it is imported, so it must be set before the first paddleocr import.
_MKLDNN_ENV_SET_BY_LIBRARY = _MKLDNN_ENV not in os.environ
if _MKLDNN_ENV_SET_BY_LIBRARY:
    os.environ[_MKLDNN_ENV] = "False"


class PaddleOcrEngine:
    name = "paddleocr"

    def __init__(
        self,
        *,
        lang: str = "ru",
        model_dir: str | Path | None = None,
        use_gpu: bool = False,
        enable_mkldnn: bool = False,
        **paddle_kwargs: Any,
    ) -> None:
        if model_dir is not None:
            path = str(Path(model_dir).resolve())
            os.environ.setdefault("PADDLEOCR_HOME", path)
            os.environ.setdefault("PADDLE_PDX_CACHE_HOME", path)

        self.enable_mkldnn = enable_mkldnn
        if _MKLDNN_ENV_SET_BY_LIBRARY:
            os.environ[_MKLDNN_ENV] = "True" if enable_mkldnn else "False"

        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except ImportError as exc:
            raise OcrEngineError(
                "PaddleOCR is not installed. Install the optional OCR dependencies "
                "in a Python version supported by PaddlePaddle, for example:\n"
                '  python -m pip install -e ".[ocr]"'
            ) from exc

        self.lang = lang
        self.model_name = _package_version("paddleocr") or "unknown"
        self._engine = _create_engine(
            PaddleOCR,
            lang=lang,
            use_gpu=use_gpu,
            **paddle_kwargs,
        )

    def recognize(self, image: np.ndarray) -> list[OcrLine]:
        if image is None or not hasattr(image, "shape"):
            raise OcrEngineError("PaddleOCR received an invalid image array")
        try:
            if hasattr(self._engine, "predict"):
                try:
                    result = self._engine.predict(image)
                except TypeError:
                    result = self._engine.ocr(image)
            else:
                result = self._engine.ocr(image)
        except Exception as exc:  # pragma: no cover - depends on PaddleOCR internals
            raise OcrEngineError(f"PaddleOCR recognition failed: {exc}") from exc
        return _parse_paddle_result(result)


def _create_engine(PaddleOCR: Any, *, lang: str, use_gpu: bool, **kwargs: Any) -> Any:
    """Instantiate PaddleOCR across v2/v3 API differences."""

    modern_kwargs = {
        "lang": lang,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        **kwargs,
    }
    try:
        return PaddleOCR(**modern_kwargs)
    except TypeError:
        legacy_kwargs = {
            "lang": lang,
            "use_angle_cls": False,
            "show_log": False,
            "use_gpu": use_gpu,
            **kwargs,
        }
        try:
            return PaddleOCR(**legacy_kwargs)
        except TypeError:
            return PaddleOCR(lang=lang, **kwargs)


def _package_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _parse_paddle_result(result: Any) -> list[OcrLine]:
    """Normalize PaddleOCR v2 and v3 result shapes into ``OcrLine`` values.

    This function is deliberately independent of PaddleOCR so it can be tested
    with fixture objects on machines where PaddleOCR is not installed.
    """

    lines: list[OcrLine] = []
    for item in _iter_items(result):
        lines.extend(_parse_item(item))
    return lines


def _iter_items(value: Any) -> Iterable[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if _looks_like_v2_line(value):
        return [value]
    if isinstance(value, (list, tuple)):
        items: list[Any] = []
        for child in value:
            if child is None:
                continue
            if _looks_like_v2_line(child):
                items.append(child)
            elif isinstance(child, (list, tuple)) and not _looks_like_v2_line(child):
                items.extend(_iter_items(child))
            else:
                items.append(child)
        return items
    if hasattr(value, "json") or hasattr(value, "to_dict"):
        return [value]
    return [value]


def _parse_item(item: Any) -> list[OcrLine]:
    if _looks_like_v2_line(item):
        return [_parse_v2_line(item)]

    mapping = _to_mapping(item)
    if mapping is not None:
        return _parse_mapping(mapping)

    if isinstance(item, (list, tuple)):
        lines: list[OcrLine] = []
        for child in item:
            lines.extend(_parse_item(child))
        return lines
    return []


def _parse_v2_line(item: Sequence[Any]) -> OcrLine:
    box = _bbox_from_box(item[0])
    payload = item[1]
    text = str(payload[0])
    confidence = float(payload[1]) if len(payload) > 1 else 0.0
    return OcrLine(text=text, confidence=confidence, box=box)


def _parse_mapping(data: Mapping[str, Any]) -> list[OcrLine]:
    data = _unwrap_mapping(data)
    texts = data.get("rec_texts", data.get("texts"))
    scores = data.get("rec_scores", data.get("scores"))
    boxes = _first_present(
        data,
        ("rec_boxes", "rec_polys", "dt_polys", "boxes"),
    )
    if texts is None:
        return []

    text_list = _as_list(texts)
    score_list = _as_list(scores) if scores is not None else []
    box_list = _as_list(boxes) if boxes is not None else []

    lines: list[OcrLine] = []
    for index, text in enumerate(text_list):
        score = score_list[index] if index < len(score_list) else 0.0
        if index < len(box_list):
            box = _bbox_from_box(box_list[index])
        else:
            box = (0.0, 0.0, 0.0, 0.0)
        lines.append(
            OcrLine(
                text=str(text),
                confidence=float(score),
                box=box,
            )
        )
    return lines


def _first_present(data: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def _unwrap_mapping(data: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = data.get("res")
    if isinstance(nested, Mapping):
        merged = dict(data)
        merged.update(nested)
        return merged
    return data


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    for attribute in ("json", "to_dict"):
        if not hasattr(value, attribute):
            continue
        candidate = getattr(value, attribute)
        if callable(candidate):
            candidate = candidate()
        if isinstance(candidate, str):
            try:
                candidate = jsonlib.loads(candidate)
            except jsonlib.JSONDecodeError:
                continue
        if isinstance(candidate, Mapping):
            return candidate
    return None


def _looks_like_v2_line(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    box, payload = value
    if not _looks_like_box(box):
        return False
    return (
        isinstance(payload, (list, tuple))
        and len(payload) >= 2
        and isinstance(payload[0], str)
        and isinstance(payload[1], (int, float))
    )


def _looks_like_box(value: Any) -> bool:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or not value:
        return False
    if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value):
        return len(value) in (4, 8)
    if all(isinstance(item, (list, tuple, np.ndarray)) for item in value):
        return len(value) >= 2
    return False


def _bbox_from_box(box: Any) -> tuple[float, float, float, float]:
    if isinstance(box, np.ndarray):
        box = box.tolist()
    if not isinstance(box, (list, tuple)) or not box:
        return (0.0, 0.0, 0.0, 0.0)

    if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in box):
        numbers = [float(item) for item in box]
        if len(numbers) == 4:
            return (numbers[0], numbers[1], numbers[2], numbers[3])
        if len(numbers) == 8:
            xs = numbers[0::2]
            ys = numbers[1::2]
            return (min(xs), min(ys), max(xs), max(ys))
        return (0.0, 0.0, 0.0, 0.0)

    points: list[tuple[float, float]] = []
    for point in box:
        if isinstance(point, np.ndarray):
            point = point.tolist()
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            points.append((float(point[0]), float(point[1])))
    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]
