from __future__ import annotations

import json
from pathlib import Path

from tft_recognition.catalog import load_catalog
from tft_recognition.fixture import load_fixture
from tft_recognition.preprocess import load_image
from tft_recognition.result import expected_traits

SCREENSHOT_ROOT = Path(__file__).resolve().parents[4] / "tests" / "ru"


def test_fixture_manifests_match_images_and_catalogs() -> None:
    for name in ("screenshot-1", "screenshot-2", "screenshot-3"):
        manifest = load_fixture(SCREENSHOT_ROOT / f"{name}.fixture.json")
        image = load_image(manifest.image)
        height, width = image.shape[:2]

        assert (width, height) == (manifest.source_width, manifest.source_height)
        assert manifest.expected_file is not None
        assert manifest.expected_file.exists()
        assert manifest.catalog is not None
        assert manifest.catalog.exists()

        pixels = manifest.crop.to_pixels(width, height)
        assert pixels.x >= 0
        assert pixels.y >= 0
        assert pixels.x + pixels.width <= width
        assert pixels.y + pixels.height <= height

        catalog = load_catalog(manifest.catalog)
        assert catalog.id == manifest.set_id
        expected = expected_traits(
            json.loads(manifest.expected_file.read_text(encoding="utf-8"))
        )
        catalog_names = {trait.display_name for trait in catalog.traits}
        assert set(expected).issubset(catalog_names)


def test_fixture_crops_are_large_enough_for_ocr() -> None:
    for name in ("screenshot-1", "screenshot-2", "screenshot-3"):
        manifest = load_fixture(SCREENSHOT_ROOT / f"{name}.fixture.json")
        pixels = manifest.crop.to_pixels(manifest.source_width, manifest.source_height)
        assert pixels.width >= 100
        assert pixels.height >= 100
