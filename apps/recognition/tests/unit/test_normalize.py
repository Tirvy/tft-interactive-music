from __future__ import annotations

import pytest

from tft_recognition.catalog import GameSet, TraitDefinition, catalog_from_mapping
from tft_recognition.normalize import (
    NormalizationConfig,
    normalize_text,
    resolve_label,
)


def game_set(*traits: TraitDefinition) -> GameSet:
    return GameSet(
        id="test-set",
        display_name="Test Set",
        data_version="test-1",
        locale="ru-RU",
        traits=tuple(traits),
    )


def test_exact_display_name(catalog) -> None:
    result = resolve_label("Инферно", catalog)
    assert result.trait is not None
    assert result.trait.id == "Inferno"
    assert result.method == "exact"
    assert result.score == 1.0


def test_case_and_whitespace_are_normalized(catalog) -> None:
    result = resolve_label("  инферно  ", catalog)
    assert result.trait is not None
    assert result.trait.id == "Inferno"
    assert result.method == "exact"


def test_unicode_nfkc_and_alias() -> None:
    catalog = game_set(
        TraitDefinition(id="KDA", display_name="K/DA", aliases=("KDA", "КДА"))
    )
    result = resolve_label("ＫＤＡ", catalog)
    assert result.trait is not None
    assert result.trait.id == "KDA"
    assert result.method == "alias"


def test_conservative_fuzzy_match() -> None:
    catalog = game_set(TraitDefinition(id="Inferno", display_name="Инферно"))
    result = resolve_label("Инфернo", catalog)  # Latin 'o' at the end
    assert result.trait is not None
    assert result.trait.id == "Inferno"
    assert result.method == "fuzzy"
    assert result.score >= 0.85


def test_unknown_label_is_not_guessed(catalog) -> None:
    result = resolve_label("Неизвестный", catalog)
    assert result.trait is None
    assert result.reason == "no_catalog_match"


def test_no_cyrillic_latin_transliteration(catalog) -> None:
    result = resolve_label("Inferno", catalog)
    assert result.trait is None
    assert result.reason == "no_catalog_match"


def test_ambiguous_match_requires_margin() -> None:
    catalog = game_set(
        TraitDefinition(id="A", display_name="ТестА"),
        TraitDefinition(id="B", display_name="ТестБ"),
    )
    result = resolve_label("ТестВ", catalog, NormalizationConfig(min_score=0.8, min_margin=0.08))
    assert result.trait is None
    assert result.reason == "ambiguous_match"


def test_alias_exact_match_wins_before_fuzzy() -> None:
    catalog = game_set(
        TraitDefinition(id="KDA", display_name="K/DA", aliases=("KDA",)),
        TraitDefinition(id="Other", display_name="KDA Music"),
    )
    result = resolve_label("kda", catalog)
    assert result.trait is not None
    assert result.trait.id == "KDA"
    assert result.method == "alias"


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  K/DA\t ") == "k/da"


def test_catalog_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        catalog_from_mapping(
            {
                "schemaVersion": 1,
                "id": "test",
                "displayName": "Test",
                "dataVersion": "1",
                "locale": "ru-RU",
                "traits": [
                    {"id": "A", "displayName": "A"},
                    {"id": "A", "displayName": "B"},
                ],
            }
        )
