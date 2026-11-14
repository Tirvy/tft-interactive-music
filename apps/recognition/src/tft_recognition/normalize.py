"""Conservative trait-label normalization."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from .catalog import GameSet, TraitDefinition


@dataclass(frozen=True)
class NormalizationConfig:
    min_score: float = 0.85
    min_margin: float = 0.08

    def validate(self) -> None:
        if not 0.0 <= self.min_score <= 1.0:
            raise ValueError("min_score must be between 0 and 1")
        if not 0.0 <= self.min_margin <= 1.0:
            raise ValueError("min_margin must be between 0 and 1")


@dataclass(frozen=True)
class NormalizationResult:
    trait: TraitDefinition | None
    method: str
    score: float
    margin: float
    reason: str | None = None
    best_candidate_id: str | None = None
    best_candidate_display_name: str | None = None


def normalize_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[\u200b-\u200d\ufeff]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.casefold()


def similarity(left: str, right: str) -> float:
    left_key = normalize_text(left)
    right_key = normalize_text(right)
    if not left_key or not right_key:
        return 0.0
    if left_key == right_key:
        return 1.0
    return SequenceMatcher(None, left_key, right_key, autojunk=False).ratio()


def resolve_label(
    raw_label: str,
    game_set: GameSet,
    config: NormalizationConfig | None = None,
) -> NormalizationResult:
    config = config or NormalizationConfig()
    config.validate()

    label = normalize_text(raw_label)
    if not label:
        return NormalizationResult(
            trait=None,
            method="unknown",
            score=0.0,
            margin=0.0,
            reason="empty_label",
        )

    exact: list[tuple[TraitDefinition, str]] = []
    for trait in game_set.traits:
        if normalize_text(trait.display_name) == label:
            exact.append((trait, "exact"))
        elif any(normalize_text(alias) == label for alias in trait.aliases):
            exact.append((trait, "alias"))

    unique_exact: dict[str, tuple[TraitDefinition, str]] = {}
    for trait, method in exact:
        unique_exact.setdefault(trait.id, (trait, method))

    if len(unique_exact) == 1:
        trait, method = next(iter(unique_exact.values()))
        return NormalizationResult(
            trait=trait,
            method=method,
            score=1.0,
            margin=1.0,
            best_candidate_id=trait.id,
            best_candidate_display_name=trait.display_name,
        )
    if len(unique_exact) > 1:
        traits = [trait for trait, _ in unique_exact.values()]
        return NormalizationResult(
            trait=None,
            method="ambiguous",
            score=1.0,
            margin=0.0,
            reason="ambiguous_match",
            best_candidate_id=traits[0].id,
            best_candidate_display_name=traits[0].display_name,
        )

    scored: list[tuple[float, TraitDefinition, str]] = []
    for trait in game_set.traits:
        best_name = ""
        best_score = 0.0
        for name in trait.names():
            score = similarity(label, name)
            if score > best_score:
                best_score = score
                best_name = name
        scored.append((best_score, trait, best_name))

    if not scored:
        return NormalizationResult(
            trait=None,
            method="unknown",
            score=0.0,
            margin=0.0,
            reason="empty_catalog",
        )

    scored.sort(key=lambda item: (-item[0], item[1].id))
    best_score, best_trait, _ = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - second_score

    if best_score < config.min_score:
        return NormalizationResult(
            trait=None,
            method="unknown",
            score=best_score,
            margin=margin,
            reason="no_catalog_match",
            best_candidate_id=best_trait.id,
            best_candidate_display_name=best_trait.display_name,
        )

    if margin < config.min_margin:
        return NormalizationResult(
            trait=None,
            method="ambiguous",
            score=best_score,
            margin=margin,
            reason="ambiguous_match",
            best_candidate_id=best_trait.id,
            best_candidate_display_name=best_trait.display_name,
        )

    return NormalizationResult(
        trait=best_trait,
        method="fuzzy",
        score=best_score,
        margin=margin,
        best_candidate_id=best_trait.id,
        best_candidate_display_name=best_trait.display_name,
    )
