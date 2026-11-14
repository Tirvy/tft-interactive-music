from __future__ import annotations

import pytest

from tft_recognition.result import expected_traits


def test_extracts_traits_and_ignores_match_data() -> None:
    payload = {
        "traits": {"Инферно": 4, "Фея": 1},
        "progress": {"stage": 3, "round": 1},
        "players": [{"health": 15}, {"health": 4}],
    }

    assert expected_traits(payload) == {"Инферно": 4, "Фея": 1}


def test_accepts_legacy_flat_payload() -> None:
    assert expected_traits({"Инферно": 2, "Фея": 1}) == {"Инферно": 2, "Фея": 1}


def test_empty_traits_are_allowed() -> None:
    assert expected_traits({"traits": {}}) == {}


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "not-an-object",
        {"traits": []},
        {"traits": {"Фея": "1"}},
        {"traits": {"Фея": True}},
        {"traits": {"Фея": -1}},
        {"traits": {1: 1}},
    ],
)
def test_rejects_invalid_payloads(payload) -> None:
    with pytest.raises(ValueError):
        expected_traits(payload)
