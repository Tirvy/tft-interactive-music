"""Command-line entry point for the recognition proof of concept."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .catalog import CatalogError, load_catalog
from .fixture import FixtureError, load_fixture
from .geometry import CropValidationError, NormalizedRect
from .normalize import NormalizationConfig
from .ocr.base import OcrEngineError
from .ocr.fake import FakeOcrEngine
from .ocr.paddle import PaddleOcrEngine
from .pipeline import PipelineConfig, recognize_path
from .preprocess import ImageLoadError, PREPROCESS_MODES, save_image
from .result import compare_expected, expected_traits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tft-recognition",
        description="Recognize TFT trait names and displayed counts from a screenshot.",
    )
    parser.add_argument("--image", help="Screenshot to process; defaults to the fixture image")
    parser.add_argument("--fixture", help="Fixture manifest with crop/set/catalog metadata")
    parser.add_argument(
        "--crop",
        help="Normalized crop override: x,y,width,height (values in 0..1)",
    )
    parser.add_argument("--catalog", help="Path to a set catalog JSON file")
    parser.add_argument("--set-id", help="Expected set ID; must match the catalog")
    parser.add_argument(
        "--ocr",
        choices=("paddle", "fake"),
        default="paddle",
        help="OCR adapter to use (default: paddle)",
    )
    parser.add_argument(
        "--ocr-lines",
        help="JSON file containing fake OCR lines; required with --ocr fake",
    )
    parser.add_argument(
        "--preprocess",
        choices=PREPROCESS_MODES,
        default="upscale3x_adaptive",
        help=(
            "Image preprocessing mode "
            "(default: upscale3x_adaptive, tuned for the fixture panels)"
        ),
    )
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument(
        "--min-ocr-confidence",
        type=float,
        default=0.5,
        help="Discard OCR lines below this confidence before parsing (default: 0.5)",
    )
    parser.add_argument("--fuzzy-min-score", type=float, default=0.85)
    parser.add_argument("--fuzzy-min-margin", type=float, default=0.08)
    parser.add_argument("--expected", help="Expected name-to-count JSON for comparison")
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit with code 4 when expected comparison fails",
    )
    parser.add_argument("--out", help="Write JSON result to this path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument(
        "--debug-dir",
        help="Opt in to saving crop/preprocessed debug images in this directory",
    )
    parser.add_argument("--model-dir", help="Local PaddleOCR model cache directory")
    parser.add_argument("--lang", default="ru", help="OCR language (default: ru)")
    parser.add_argument(
        "--paddle-enable-mkldnn",
        action="store_true",
        help=(
            "Allow PaddleOCR to use oneDNN/MKLDNN. Disabled by default because "
            "PaddlePaddle 3.3 fails on Windows with a PIR attribute error."
        ),
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with code 3 when recognition status is 'error'",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = _run(args)
    except OcrEngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (
        CropValidationError,
        FixtureError,
        CatalogError,
        ImageLoadError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = result.to_json(pretty=args.pretty)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    print(output)

    if result.status == "error" and args.fail_on_error:
        return 3
    comparison = result.diagnostics.get("expectedComparison")
    if args.fail_on_mismatch and isinstance(comparison, dict) and not comparison.get("passed"):
        return 4
    return 0


def _run(args: argparse.Namespace):
    fixture = load_fixture(args.fixture) if args.fixture else None

    image_path = Path(args.image) if args.image else (fixture.image if fixture else None)
    if image_path is None:
        raise ValueError("provide --image or a --fixture manifest with an image")

    if args.crop:
        rect = NormalizedRect.from_string(args.crop)
    elif fixture is not None:
        rect = fixture.crop
    else:
        raise ValueError("provide --crop or a --fixture manifest with a crop")

    catalog_path = Path(args.catalog) if args.catalog else (fixture.catalog if fixture else None)
    if catalog_path is None:
        raise ValueError("provide --catalog or a --fixture manifest with a catalog")
    game_set = load_catalog(catalog_path)

    if fixture is not None and fixture.set_id != game_set.id:
        raise ValueError(
            f"fixture set ID {fixture.set_id!r} does not match catalog ID {game_set.id!r}"
        )
    if args.set_id is not None and args.set_id != game_set.id:
        raise ValueError(
            f"--set-id {args.set_id!r} does not match catalog ID {game_set.id!r}"
        )

    if args.ocr == "fake":
        if not args.ocr_lines:
            raise ValueError("--ocr fake requires --ocr-lines")
        engine = FakeOcrEngine.from_file(args.ocr_lines)
    else:
        engine = PaddleOcrEngine(
            lang=args.lang,
            model_dir=args.model_dir,
            enable_mkldnn=args.paddle_enable_mkldnn,
        )

    config = PipelineConfig(
        game_set=game_set,
        preprocess_mode=args.preprocess,
        min_confidence=args.min_confidence,
        min_ocr_confidence=args.min_ocr_confidence,
        normalization=NormalizationConfig(
            min_score=args.fuzzy_min_score,
            min_margin=args.fuzzy_min_margin,
        ),
    )
    run = recognize_path(image_path, rect, engine, config)

    expected_path = Path(args.expected) if args.expected else (
        fixture.expected_file if fixture is not None else None
    )
    if expected_path is not None:
        payload = json.loads(Path(expected_path).read_text(encoding="utf-8"))
        try:
            expected = expected_traits(payload)
        except ValueError as exc:
            raise ValueError(f"expected file {expected_path}: {exc}") from exc
        run.result.diagnostics["expectedComparison"] = compare_expected(run.result, expected)
        run.result.diagnostics["expectedFile"] = str(expected_path)

    if args.debug_dir:
        debug_dir = Path(args.debug_dir)
        artifacts: list[str] = []
        for filename, image in run.debug_artifacts().items():
            target = debug_dir / filename
            save_image(target, image)
            artifacts.append(str(target))
        run.result.diagnostics["debugArtifacts"] = artifacts

    return run.result


def _entrypoint() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
