"""Versioned set catalogs used by the recognition proof of concept."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class CatalogError(ValueError):
    """Raised when a set catalog cannot be loaded or validated."""


@dataclass(frozen=True)
class TraitDefinition:
    id: str
    display_name: str
    aliases: tuple[str, ...] = ()
    breakpoints: tuple[int, ...] = ()

    def names(self) -> tuple[str, ...]:
        """All catalog names for this trait, with the display name first."""

        return (self.display_name, *self.aliases)


@dataclass(frozen=True)
class GameSet:
    id: str
    display_name: str
    data_version: str
    locale: str
    traits: tuple[TraitDefinition, ...]

    def trait_by_id(self, trait_id: str) -> TraitDefinition | None:
        for trait in self.traits:
            if trait.id == trait_id:
                return trait
        return None


def load_catalog(path: str | Path) -> GameSet:
    catalog_path = Path(path)
    try:
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogError(f"could not read catalog {catalog_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"catalog {catalog_path} is not valid JSON: {exc}") from exc
    return catalog_from_mapping(data, where=str(catalog_path))


def catalog_from_mapping(data: Mapping[str, Any], *, where: str = "catalog") -> GameSet:
    if not isinstance(data, Mapping):
        raise CatalogError(f"{where} must be an object")

    schema_version = data.get("schemaVersion")
    if schema_version != 1:
        raise CatalogError(f"{where}.schemaVersion must be 1, got {schema_version!r}")

    for field in ("id", "displayName", "dataVersion", "locale", "traits"):
        if field not in data:
            raise CatalogError(f"{where} is missing {field}")

    for field in ("id", "displayName", "dataVersion", "locale"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise CatalogError(f"{where}.{field} must be a non-empty string")

    raw_traits = data["traits"]
    if not isinstance(raw_traits, list) or not raw_traits:
        raise CatalogError(f"{where}.traits must be a non-empty array")

    traits: list[TraitDefinition] = []
    seen_ids: set[str] = set()
    seen_names: dict[str, str] = {}
    for index, raw_trait in enumerate(raw_traits):
        trait_where = f"{where}.traits[{index}]"
        if not isinstance(raw_trait, Mapping):
            raise CatalogError(f"{trait_where} must be an object")

        trait_id = raw_trait.get("id")
        display_name = raw_trait.get("displayName")
        if not isinstance(trait_id, str) or not trait_id.strip():
            raise CatalogError(f"{trait_where}.id must be a non-empty string")
        if not isinstance(display_name, str) or not display_name.strip():
            raise CatalogError(f"{trait_where}.displayName must be a non-empty string")
        if trait_id in seen_ids:
            raise CatalogError(f"{trait_where}.id duplicates {trait_id!r}")
        seen_ids.add(trait_id)

        raw_aliases = raw_trait.get("aliases", [])
        if raw_aliases is None:
            raw_aliases = []
        if not isinstance(raw_aliases, list) or not all(
            isinstance(alias, str) and alias.strip() for alias in raw_aliases
        ):
            raise CatalogError(f"{trait_where}.aliases must be an array of non-empty strings")

        raw_breakpoints = raw_trait.get("breakpoints", [])
        if raw_breakpoints is None:
            raw_breakpoints = []
        if not isinstance(raw_breakpoints, list) or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in raw_breakpoints
        ):
            raise CatalogError(
                f"{trait_where}.breakpoints must be an array of positive integers"
            )
        if raw_breakpoints != sorted(raw_breakpoints):
            raise CatalogError(f"{trait_where}.breakpoints must be sorted ascending")

        for name in (display_name, *raw_aliases):
            key = _name_key(name)
            previous = seen_names.get(key)
            if previous is not None and previous != trait_id:
                raise CatalogError(
                    f"{trait_where} name {name!r} is already used by trait {previous!r}"
                )
            seen_names[key] = trait_id

        traits.append(
            TraitDefinition(
                id=trait_id,
                display_name=display_name,
                aliases=tuple(raw_aliases),
                breakpoints=tuple(raw_breakpoints),
            )
        )

    return GameSet(
        id=data["id"],
        display_name=data["displayName"],
        data_version=data["dataVersion"],
        locale=data["locale"],
        traits=tuple(traits),
    )


def _name_key(value: str) -> str:
    import unicodedata

    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
