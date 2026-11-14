# Trait-panel recognition proof of concept

Python proof of concept for reading TFT trait names and displayed counts
from a screenshot of the visible trait panel. It is deliberately smaller
than the desktop application: there is no live capture, calibration UI,
temporal composition validation, rule engine, or audio playback here.

The POC exists to answer one question: can a screenshot crop be turned
into reliable `trait name -> displayed count` rows with traceable raw OCR
data and diagnostic output?

## What it does

-   Crops an image using a normalized `x, y, width, height` rectangle.
-   Validates crop bounds and source dimensions.
-   Preprocesses the crop (upscale, grayscale, CLAHE, adaptive threshold).
-   Runs OCR through an adapter (`fake` or `paddleocr`).
-   Parses labels, counts, and breakpoint sublines from OCR lines.
-   Normalizes labels against a versioned set catalog.
-   Emits a versioned JSON result with traits, unknown rows, confidence,
    and diagnostics.
-   Keeps every OCR line either assigned to a row or recorded as ignored.
-   Provides fixture-based unit tests and two real-screenshot integration
    tests.

## What it does not do

-   Capture or watch a live game window.
-   Calibrate the crop through a UI.
-   Infer traits from champions or board units.
-   Validate composition over time or keep last-known-good state.
-   Evaluate music rules or control audio.
-   Ship an authoritative game-data catalog.

## Layout

```text
apps/recognition/
  pyproject.toml
  src/tft_recognition/
    geometry.py       normalized crop -> pixel crop
    preprocess.py     image loading and preprocessing modes
    ocr/base.py       OCR adapter contract
    ocr/fake.py       deterministic fake OCR for tests
    ocr/paddle.py     PaddleOCR adapter and result normalization
    parse.py          OCR lines -> count/label/breakpoint rows
    catalog.py        set catalog loading and validation
    normalize.py      exact/alias/fuzzy trait resolution
    pipeline.py       crop -> OCR -> parse -> normalize -> result
    fixture.py        fixture manifest loading
    result.py         versioned result schema and expected comparison
    cli.py            command-line entry point
  tests/
    unit/             hermetic tests using fake OCR
    integration/      real PaddleOCR tests, marked `ocr`
    fixtures/         catalog and fake OCR fixtures
```

## Setup

### Core tests (no OCR engine required)

The core path only needs NumPy, OpenCV, and pytest. Python 3.10+ is
enough.

```powershell
cd apps/recognition
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Expected result: all unit tests pass; the two real-OCR tests are
skipped because PaddleOCR is not installed.

### Real OCR

PaddlePaddle 3.3 did not publish a wheel for the local Python 3.14, so the
real OCR environment uses Python 3.12.

```powershell
cd apps/recognition
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -e ".[dev,ocr]"
.\.venv312\Scripts\python.exe -m pytest -q
```

The first run downloads the `PP-OCRv5_server_det` and
`eslav_PP-OCRv5_mobile_rec` models into the PaddleX cache. The integration
tests are marked `ocr`; they run as part of the normal pytest invocation
when PaddleOCR is installed, or can be selected explicitly:

```powershell
.\.venv312\Scripts\python.exe -m pytest -m ocr -q
```

## Usage

### Fake OCR demo

Use the fake adapter when you want to inspect the parser, normalization,
and result schema without PaddleOCR. The included fake lines describe two
trait rows.

```powershell
cd apps/recognition
.\.venv\Scripts\python.exe -m tft_recognition.cli `
  --fixture ..\..\tests\ru\screenshot-1.fixture.json `
  --ocr fake `
  --ocr-lines tests\fixtures\ocr\demo-lines.json `
  --preprocess raw `
  --pretty
```

### Real PaddleOCR

```powershell
cd apps/recognition
.\.venv312\Scripts\python.exe -m tft_recognition.cli `
  --fixture ..\..\tests\ru\screenshot-1.fixture.json `
  --pretty `
  --out result.json
```

Add `--fail-on-mismatch` to exit with code `4` when an expected
name/count fixture does not match, or `--fail-on-error` to exit with code
`3` when recognition itself fails.

### Main CLI options

| Option | Purpose |
| --- | --- |
| `--fixture` | Fixture manifest with image, crop, set, catalog, and expected file. |
| `--image`, `--crop` | Override the fixture image or normalized crop. |
| `--catalog`, `--set-id` | Override or assert the set catalog. |
| `--ocr paddle\|fake` | Choose the OCR adapter. |
| `--ocr-lines` | Fake OCR JSON lines; required for `--ocr fake`. |
| `--preprocess` | Preprocessing mode; default `upscale3x_adaptive`. |
| `--min-ocr-confidence` | Hard OCR floor; default `0.5`. |
| `--min-confidence` | Row confidence warning threshold; default `0.6`. |
| `--fuzzy-min-score`, `--fuzzy-min-margin` | Fuzzy matching policy; defaults `0.85` and `0.08`. |
| `--debug-dir` | Opt in to writing crop/preprocessed debug images. |
| `--out`, `--pretty` | Write and format the JSON result. |

## Fixtures

The two screenshots under `tests/ru/` are Russian TFT Set 18 panels.
Their sidecar manifests were added next to the existing expected JSON so
the original `screenshot-N.json` files stay untouched:

```text
tests/ru/screenshot-1.png
tests/ru/screenshot-1.json
tests/ru/screenshot-1.fixture.json
```

Each manifest stores:

-   `image`: screenshot filename.
-   `expectedFile`: expected match data.
-   `setId`, `locale`: catalog identity.
-   `source.width`, `source.height`: validated screenshot dimensions.
-   `crop`: normalized panel rectangle.
-   `catalog`: path to the fixture Set 18 catalog.
-   `notes`: crop observations.

The expected file stores traits under a `traits` object. It may also
carry match metadata such as `progress` and `players`; recognition
currently reads only `traits` and ignores the rest:

```json
{
  "traits": {
    "Инферно": 4,
    "Страж": 4
  },
  "progress": {"stage": 3, "round": 1},
  "players": [{"health": 15}, {"health": 4}]
}
```

A legacy bare `{ "name": count }` object is still accepted.

The fixture catalog under
`tests/fixtures/catalog/set-18-ru.fixture.json` is illustrative data
cross-checked against a secondary community source. It is not an
authoritative Riot data source and must be replaced before shipping.

## Result schema

A result contains:

-   `type` and `schemaVersion`.
-   `captureTimestamp` and `setId`.
-   `status`: `ok`, `partial`, `unavailable`, or `error`.
-   `traits`: normalized trait ID, display name, raw text, count,
    match method/score/margin, and optional confidence.
-   `unknownRows`: raw text, optional count, reason, confidence, bounding
    box, and optional best candidate.
-   `diagnostics`: source size, crop, preprocessing, OCR engine/model,
    scale, ignored lines, timings, warnings, and expected comparison.

`count` is always the displayed count. Breakpoint text such as
`2 > 3 > 5 > 7` or `1/2` is retained in row parsing and ignored lines but
is never used as the count.

Status rules:

-   `ok`: at least one row parsed, no unknown rows, no low-confidence
    warnings.
-   `partial`: at least one row parsed, but some rows are unknown,
    ambiguous, duplicated, or below the warning threshold.
-   `unavailable`: no trait rows were parsed.
-   `error`: the OCR adapter raised an error.

## Preprocessing and OCR scale

OCR engines report boxes in the coordinate space of the image they
receive. Upscaling modes therefore return a scale factor, and the
pipeline maps boxes back to original crop coordinates before parsing.
This keeps row diagnostics consistent across modes.

The default mode, `upscale3x_adaptive`, triples the crop and applies a
Gaussian adaptive threshold. It was selected on the two tracked fixtures
because it detected the thin `1` count glyphs that raw OCR missed. Other
modes remain available for benchmarking and future panels. See
`docs/OCR_BENCHMARK.md`.

## PaddleOCR notes

-   The adapter disables PaddleX MKLDNN by default. PaddlePaddle 3.3 on
    Windows fails inside oneDNN with
    `ConvertPirAttribute2RuntimeAttribute not support
    [pir::ArrayAttribute<pir::DoubleAttribute>]`.
-   The environment flag is set before `paddleocr` is imported. If a
    process imports `paddleocr` before this package, the flag may be read
    too late.
-   `--paddle-enable-mkldnn` opts back in.
-   PaddleOCR results are normalized from both v2-style nested lists and
    v3-style `rec_texts`/`rec_scores`/`rec_polys` mappings.

## Known limitations

-   Only two Russian Set 18 screenshots are covered.
-   The Set 18 catalog is fixture data, not an authoritative data pack.
-   Adaptive thresholding is tuned for these dark, translucent panels.
    Another UI scale, font, or background may need a different mode.
-   OCR sometimes drops spaces between words (`Крепкаясвязь`); conservative
    fuzzy matching resolves these cases but records `method: "fuzzy"`.
-   Breakpoint text is diagnostic only; it is not yet mapped to catalog
    breakpoints.
-   No temporal stability filter is applied here. A future worker should
    require repeated consistent readings before publishing a composition.
-   Screenshot retention and licensing remain unresolved. Do not move or
    delete the tracked fixtures without confirmation.

## Tests

Hermetic unit tests cover geometry, preprocessing, parsing, normalization,
catalog validation, fixtures, the CLI, and Paddle result normalization.
Real-screenshot tests assert that both fixtures produce exactly the
expected display-name/count pairs and an `ok` status.

Last verified locally:

-   Python 3.14, core environment: `69 passed, 2 skipped`.
-   Python 3.12, PaddleOCR environment: `71 passed`.
