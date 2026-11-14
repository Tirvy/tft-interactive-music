"""Fixture manifest loading for screenshot-based tests and the CLI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .geometry import CropValidationError, NormalizedRect


class FixtureError(ValueError):
    """Raised when a fixture manifest is invalid."""


@dataclass(frozen=True)
class FixtureManifest:
    image: Path
    set_id: str
    locale: str
    source_width: int
    source_height: int
    crop: NormalizedRect
    expected_file: Path | None = None
    catalog: Path | None = None
    notes: str | None = None
    manifest_path: Path | None = None


def load_fixture(path: str | Path) -> FixtureManifest:
    fixture_path = Path(path).resolve()
    try:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FixtureError(f"could not read fixture {fixture_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise FixtureError(f"fixture {fixture_path} is not valid JSON: {exc}") from exc
    return fixture_from_mapping(
        data,
        base_dir=fixture_path.parent,
        manifest_path=fixture_path,
        where=str(fixture_path),
    )


def fixture_from_mapping(
    data: Mapping[str, Any],
    *,
    base_dir: Path,
    manifest_path: Path | None = None,
    where: str = "fixture",
) -> FixtureManifest:
    if not isinstance(data, Mapping):
        raise FixtureError(f"{where} must be an object")
    if data.get("schemaVersion") != 1:
        raise FixtureError(f"{where}.schemaVersion must be 1")

    for field in ("image", "setId", "locale", "source", "crop"):
        if field not in data:
            raise FixtureError(f"{where} is missing {field}")

    image_value = data["image"]
    set_id = data["setId"]
    locale = data["locale"]
    notes = data.get("notes")
    if not isinstance(image_value, str) or not image_value.strip():
        raise FixtureError(f"{where}.image must be a non-empty string")
    if not isinstance(set_id, str) or not set_id.strip():
        raise FixtureError(f"{where}.setId must be a non-empty string")
    if not isinstance(locale, str) or not locale.strip():
        raise FixtureError(f"{where}.locale must be a non-empty string")
    if notes is not None and not isinstance(notes, str):
        raise FixtureError(f"{where}.notes must be a string")

    source = data["source"]
    if not isinstance(source, Mapping):
        raise FixtureError(f"{where}.source must be an object")
    source_width = _positive_int(source.get("width"), f"{where}.source.width")
    source_height = _positive_int(source.get("height"), f"{where}.source.height")

    try:
        crop = NormalizedRect.from_mapping(data["crop"], where=f"{where}.crop")
        crop.to_pixels(source_width, source_height)
    except CropValidationError as exc:
        raise FixtureError(str(exc)) from exc

    image_path = _resolve_path(base_dir, image_value)
    expected_file = _optional_path(base_dir, data.get("expectedFile"), f"{where}.expectedFile")
    catalog = _optional_path(base_dir, data.get("catalog"), f"{where}.catalog")

    return FixtureManifest(
        manifest_path=manifest_path,
        image=image_path,
        set_id=set_id,
        locale=locale,
        source_width=source_width,
        source_height=source_height,
        crop=crop,
        expected_file=expected_file,
        catalog=catalog,
        notes=notes,
    )


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def _optional_path(base_dir: Path, value: Any, field: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise FixtureError(f"{field} must be a non-empty string")
    return _resolve_path(base_dir, value)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FixtureError(f"{field} must be a positive integer")
    return value
