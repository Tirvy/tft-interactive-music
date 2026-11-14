"""Turn raw OCR lines into count/label rows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .ocr.base import OcrLine

COUNT_PATTERN = re.compile(r"^\d{1,2}$")
NUMERIC_PATTERN = re.compile(r"^\d{1,4}$")
BREAKPOINT_PATTERN = re.compile(
    r"^\d{1,2}(?:\s*(?:[>/·•→-])\s*\d{1,2})+$"
)
LEADING_COUNT_PATTERN = re.compile(
    r"^\s*(?P<count>\d{1,2})\s*(?P<label>[^\W\d_].*)$",
    re.UNICODE,
)
TRAILING_BREAKPOINT_PATTERN = re.compile(
    r"\s+(?P<breakpoints>\d{1,2}(?:\s*(?:[>/·•→-])\s*\d{1,2})+)\s*$"
)


@dataclass(frozen=True)
class IgnoredLine:
    text: str
    reason: str
    confidence: float | None = None
    box: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "reason": self.reason,
            "confidence": self.confidence,
            "bbox": list(self.box) if self.box is not None else None,
        }


@dataclass(frozen=True)
class RawRow:
    raw_text: str
    count_text: str | None
    label_text: str | None
    confidence: float | None
    bbox: tuple[float, float, float, float] | None
    breakpoint_text: str | None = None
    source_lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParseResult:
    rows: tuple[RawRow, ...]
    ignored_lines: tuple[IgnoredLine, ...]


@dataclass
class _LineInfo:
    line: OcrLine
    text: str
    kind: str  # label, count, breakpoint


@dataclass
class _RowGroup:
    lines: list[_LineInfo] = field(default_factory=list)
    count_line: _LineInfo | None = None
    breakpoint_lines: list[_LineInfo] = field(default_factory=list)
    count_from_text: str | None = None
    breakpoint_from_text: str | None = None
    label_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def label_bbox(self) -> tuple[float, float, float, float]:
        return _union_boxes([line.line.box for line in self.lines])

    @property
    def all_lines(self) -> list[_LineInfo]:
        result = list(self.lines)
        if self.count_line is not None:
            result.append(self.count_line)
        result.extend(self.breakpoint_lines)
        return result

    @property
    def bbox(self) -> tuple[float, float, float, float] | None:
        boxes = [line.line.box for line in self.all_lines]
        if not boxes:
            return None
        return _union_boxes(boxes)


def parse_ocr_lines(lines: Sequence[OcrLine]) -> ParseResult:
    ignored: list[IgnoredLine] = []
    label_lines: list[_LineInfo] = []
    numeric_lines: list[_LineInfo] = []
    breakpoint_lines: list[_LineInfo] = []

    for line in lines:
        text = line.text.strip()
        if not text:
            ignored.append(
                IgnoredLine(
                    text=line.text,
                    reason="empty_text",
                    confidence=line.confidence,
                    box=line.box,
                )
            )
            continue
        if _has_letter(text):
            label_lines.append(_LineInfo(line=line, text=text, kind="label"))
        elif NUMERIC_PATTERN.fullmatch(text):
            numeric_lines.append(_LineInfo(line=line, text=text, kind="numeric"))
        elif BREAKPOINT_PATTERN.fullmatch(text):
            breakpoint_lines.append(
                _LineInfo(line=line, text=text, kind="breakpoint")
            )
        else:
            ignored.append(
                IgnoredLine(
                    text=text,
                    reason="non_trait_noise",
                    confidence=line.confidence,
                    box=line.box,
                )
            )

    groups: list[_RowGroup] = []
    for label_line in label_lines:
        group = _find_group(groups, label_line.line.box)
        if group is None:
            group = _RowGroup()
            groups.append(group)
        group.lines.append(label_line)

    for group in groups:
        group.lines.sort(key=lambda item: (item.line.box[0], item.line.box[1]))
        combined = " ".join(item.text for item in group.lines)
        count_text, label_text, breakpoint_text = _split_merged_text(combined)
        group.count_from_text = count_text
        group.label_text = label_text
        group.breakpoint_from_text = breakpoint_text
        if not label_text:
            group.warnings.append("missing_label")

    assigned: set[int] = set()
    _assign_counts(groups, numeric_lines, assigned)
    _assign_breakpoints(groups, numeric_lines, breakpoint_lines, assigned, ignored)

    rows: list[RawRow] = []
    for group in groups:
        if not group.label_text:
            ignored.append(
                IgnoredLine(
                    text=" ".join(item.text for item in group.lines),
                    reason="missing_label",
                    confidence=_min_confidence(group.lines),
                    box=group.label_bbox,
                )
            )
            continue

        count_text = group.count_from_text
        if count_text is None and group.count_line is not None:
            count_text = group.count_line.text
        if count_text is not None and not COUNT_PATTERN.fullmatch(count_text):
            group.warnings.append("invalid_count")
            count_text = None
        if count_text is None:
            group.warnings.append("missing_count")

        breakpoint_parts: list[str] = []
        if group.breakpoint_from_text:
            breakpoint_parts.append(group.breakpoint_from_text)
        breakpoint_parts.extend(item.text for item in group.breakpoint_lines)
        breakpoint_text = " | ".join(breakpoint_parts) if breakpoint_parts else None

        confidence_lines = [item.line for item in group.lines]
        if group.count_line is not None:
            confidence_lines.append(group.count_line.line)
        confidence = _min_confidence(confidence_lines)

        source_lines = tuple(item.text for item in group.all_lines)
        raw_order = sorted(
            group.all_lines,
            key=lambda item: (
                0 if item.kind == "count" else 1 if item.kind == "label" else 2,
                item.line.box[0],
                item.line.box[1],
            ),
        )
        raw_text = " ".join(item.text for item in raw_order)

        rows.append(
            RawRow(
                raw_text=raw_text,
                count_text=count_text,
                label_text=group.label_text,
                confidence=confidence,
                bbox=group.bbox,
                breakpoint_text=breakpoint_text,
                source_lines=source_lines,
                warnings=tuple(dict.fromkeys(group.warnings)),
            )
        )

    rows.sort(
        key=lambda row: (
            row.bbox[1] if row.bbox is not None else float("inf"),
            row.bbox[0] if row.bbox is not None else float("inf"),
        )
    )
    return ParseResult(rows=tuple(rows), ignored_lines=tuple(ignored))


def _assign_counts(
    groups: Sequence[_RowGroup],
    numeric_lines: Sequence[_LineInfo],
    assigned: set[int],
) -> None:
    """Assign at most one nearest numeric line to each label row.

    The displayed count sits to the left of the label and shares its vertical
    band. Breakpoint sublines sit below the label, so they are deliberately
    excluded here and handled by ``_assign_breakpoints``.
    """

    for group in groups:
        if group.count_from_text is not None:
            continue
        label_box = group.label_bbox
        candidates: list[tuple[float, float, _LineInfo]] = []
        for item in numeric_lines:
            if id(item) in assigned or not COUNT_PATTERN.fullmatch(item.text):
                continue
            box = item.line.box
            if not _same_row(label_box, box) or not _is_left_of(box, label_box):
                continue
            gap = label_box[0] - box[2]
            distance = abs(_center_y(box) - _center_y(label_box))
            candidates.append((gap, distance, item))

        if not candidates:
            continue
        candidates.sort(key=lambda value: (value[0], value[1], value[2].line.box[1]))
        chosen = candidates[0][2]
        chosen.kind = "count"
        group.count_line = chosen
        assigned.add(id(chosen))


def _assign_breakpoints(
    groups: Sequence[_RowGroup],
    numeric_lines: Sequence[_LineInfo],
    breakpoint_lines: Sequence[_LineInfo],
    assigned: set[int],
    ignored: list[IgnoredLine],
) -> None:
    """Attach leftover numeric and breakpoint lines below their label row.

    PaddleOCR often returns compact breakpoint text such as ``11`` or ``246``
    instead of the visible ``1 > 1`` or ``2 > 4 > 6``. Those runs are numeric
    but not counts, so they are reclassified here by position.
    """

    for item in [*numeric_lines, *breakpoint_lines]:
        if id(item) in assigned:
            continue
        group = _find_breakpoint_group(groups, item.line.box)
        if group is None:
            reason = (
                "unassigned_count"
                if item.kind == "numeric" and COUNT_PATTERN.fullmatch(item.text)
                else "unassigned_breakpoint"
            )
            ignored.append(
                IgnoredLine(
                    text=item.text,
                    reason=reason,
                    confidence=item.line.confidence,
                    box=item.line.box,
                )
            )
            continue
        item.kind = "breakpoint"
        group.breakpoint_lines.append(item)
        assigned.add(id(item))

    for group in groups:
        group.breakpoint_lines.sort(
            key=lambda item: (item.line.box[1], item.line.box[0])
        )


def _has_letter(text: str) -> bool:
    return any(character.isalpha() for character in text)


def _split_merged_text(text: str) -> tuple[str | None, str, str | None]:
    count_text: str | None = None
    label_text = text.strip()
    breakpoint_text: str | None = None

    match = LEADING_COUNT_PATTERN.match(label_text)
    if match is not None:
        count_text = match.group("count")
        label_text = match.group("label").strip()

    trailing = TRAILING_BREAKPOINT_PATTERN.search(label_text)
    if trailing is not None:
        breakpoint_text = trailing.group("breakpoints").strip()
        label_text = label_text[: trailing.start()].strip()

    return count_text, label_text, breakpoint_text


def _find_group(
    groups: Sequence[_RowGroup],
    box: tuple[float, float, float, float],
) -> _RowGroup | None:
    for group in groups:
        if _same_row(group.label_bbox, box):
            return group
    return None


def _find_breakpoint_group(
    groups: Sequence[_RowGroup],
    box: tuple[float, float, float, float],
) -> _RowGroup | None:
    best: tuple[float, _RowGroup] | None = None
    for group in groups:
        label_box = group.label_bbox
        horizontal_overlap = min(box[2], label_box[2]) - max(box[0], label_box[0])
        if horizontal_overlap <= 0:
            continue
        gap = box[1] - label_box[3]
        height = max(1.0, label_box[3] - label_box[1])
        if gap < -0.3 * height or gap > 0.9 * height:
            continue
        distance = abs(_center_y(box) - _center_y(label_box))
        if best is None or distance < best[0]:
            best = (distance, group)
    return best[1] if best is not None else None


def _same_row(
    left_box: tuple[float, float, float, float],
    right_box: tuple[float, float, float, float],
) -> bool:
    left_height = max(0.0, left_box[3] - left_box[1])
    right_height = max(0.0, right_box[3] - right_box[1])
    if left_height <= 0 or right_height <= 0:
        return False
    overlap = max(0.0, min(left_box[3], right_box[3]) - max(left_box[1], right_box[1]))
    if overlap >= 0.5 * min(left_height, right_height):
        return True
    center_distance = abs(_center_y(left_box) - _center_y(right_box))
    return center_distance <= 0.35 * max(left_height, right_height)


def _is_left_of(
    left_box: tuple[float, float, float, float],
    right_box: tuple[float, float, float, float],
) -> bool:
    """Return True when ``left_box`` sits immediately left of ``right_box``.

    Count text touches the label column. Breakpoint fragments can also start
    near the label's left edge, so the right edge of the candidate must stay
    inside the label's left margin instead of merely overlapping the label.
    """

    height = max(1.0, right_box[3] - right_box[1])
    return left_box[2] <= right_box[0] + 0.1 * height


def _center_y(box: tuple[float, float, float, float]) -> float:
    return (box[1] + box[3]) / 2.0


def _union_boxes(
    boxes: Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _min_confidence(lines: Sequence[OcrLine | _LineInfo]) -> float | None:
    values = [
        line.confidence if isinstance(line, OcrLine) else line.line.confidence
        for line in lines
        if (line.confidence if isinstance(line, OcrLine) else line.line.confidence)
        is not None
    ]
    return min(values) if values else None
