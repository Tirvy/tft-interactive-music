"""Versioned recognition result models."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .parse import IgnoredLine


STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class TraitResult:
    trait_id: str
    display_name: str
    raw_text: str
    count: int
    confidence: float | None
    match_method: str
    match_score: float
    match_margin: float

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "traitId": self.trait_id,
            "displayName": self.display_name,
            "rawText": self.raw_text,
            "count": self.count,
            "match": {
                "method": self.match_method,
                "score": round(self.match_score, 6),
                "margin": round(self.match_margin, 6),
            },
        }
        if self.confidence is not None:
            result["confidence"] = round(self.confidence, 6)
        return result


@dataclass(frozen=True)
class UnknownRowResult:
    raw_text: str
    count: int | None
    reason: str
    confidence: float | None = None
    bbox: tuple[float, float, float, float] | None = None
    candidate_id: str | None = None
    candidate_display_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "rawText": self.raw_text,
            "count": self.count,
            "reason": self.reason,
        }
        if self.confidence is not None:
            result["confidence"] = round(self.confidence, 6)
        if self.bbox is not None:
            result["bbox"] = [round(value, 3) for value in self.bbox]
        if self.candidate_id is not None:
            result["candidateId"] = self.candidate_id
        if self.candidate_display_name is not None:
            result["candidateDisplayName"] = self.candidate_display_name
        return result


@dataclass(frozen=True)
class RecognitionResult:
    capture_timestamp: str
    set_id: str
    status: str
    traits: tuple[TraitResult, ...] = ()
    unknown_rows: tuple[UnknownRowResult, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1
    type: str = "recognition.result"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "schemaVersion": self.schema_version,
            "captureTimestamp": self.capture_timestamp,
            "setId": self.set_id,
            "status": self.status,
            "traits": [trait.to_dict() for trait in self.traits],
            "unknownRows": [row.to_dict() for row in self.unknown_rows],
            "diagnostics": _json_safe(self.diagnostics),
        }

    def to_json(self, *, pretty: bool = False) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=False,
        )


def ignored_lines_to_dicts(lines: tuple[IgnoredLine, ...]) -> list[dict[str, Any]]:
    return [line.to_dict() for line in lines]


def expected_traits(payload: Any) -> dict[str, int]:
    """Extract ``display name -> count`` pairs from an expected fixture.

    Current fixtures store expectations under ``traits`` and add optional
    match data such as ``progress`` and ``players``. Those extras are
    ignored here. A bare name-to-count object is still accepted for older
    fixtures.
    """

    if not isinstance(payload, dict):
        raise ValueError("expected fixture must be a JSON object")

    traits = payload["traits"] if "traits" in payload else payload
    if not isinstance(traits, dict):
        raise ValueError(
            "expected 'traits' must be a JSON object of name -> integer count"
        )
    if not all(
        isinstance(name, str)
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
        for name, count in traits.items()
    ):
        raise ValueError(
            "expected 'traits' must map display names to non-negative integers"
        )
    return dict(traits)


def compare_expected(
    result: RecognitionResult,
    expected: dict[str, int],
) -> dict[str, Any]:
    """Compare normalized display-name/count pairs against an expected map.

    The existing repository fixtures use localized display names as keys, so
    this comparison deliberately stays at the display-name boundary.
    """

    actual = {trait.display_name: trait.count for trait in result.traits}
    missing = [name for name in expected if name not in actual]
    extra = [name for name in actual if name not in expected]
    mismatches: dict[str, dict[str, int]] = {}
    for name, expected_count in expected.items():
        if name in actual and actual[name] != expected_count:
            mismatches[name] = {"expected": expected_count, "actual": actual[name]}

    matched = len(expected) - len(missing) - len(mismatches)
    return {
        "passed": not missing and not extra and not mismatches,
        "expectedCount": len(expected),
        "actualCount": len(actual),
        "matched": matched,
        "missing": missing,
        "extra": extra,
        "countMismatches": mismatches,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except (TypeError, ValueError):
            return value
    return value
