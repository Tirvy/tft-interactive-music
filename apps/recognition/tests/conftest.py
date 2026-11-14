from __future__ import annotations

from pathlib import Path

import pytest

from tft_recognition.catalog import load_catalog

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = TEST_ROOT / "fixtures"
SCREENSHOT_ROOT = REPO_ROOT / "tests" / "ru"


@pytest.fixture
def catalog():
    return load_catalog(FIXTURE_ROOT / "catalog" / "set-18-ru.fixture.json")
