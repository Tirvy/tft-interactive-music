# OCR benchmark: trait-panel recognition POC

Benchmark notes for choosing the default preprocessing mode and OCR
confidence floor on the two tracked Russian Set 18 fixtures. This is a
record of what was tried and observed, not a general OCR accuracy claim.

## Environment

| Item | Value |
| --- | --- |
| OS | Windows |
| Python | 3.12 (`apps/recognition/.venv312`) |
| PaddleOCR | 3.7.0 |
| PaddlePaddle | 3.3.1 (CPU, oneDNN/MKLDNN disabled) |
| Detection model | `PP-OCRv5_server_det` |
| Recognition model | `eslav_PP-OCRv5_mobile_rec` |
| OpenCV | as pinned by the recognition package |

OneDNN is disabled with `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False`
because PaddlePaddle 3.3 on Windows raises
`ConvertPirAttribute2RuntimeAttribute not support
[pir::ArrayAttribute<pir::DoubleAttribute>]`. See `DECISIONS.md`.

## Fixtures

| Fixture | Resolution | Expected rows | Crop (normalized) |
| --- | --- | --- | --- |
| `tests/ru/screenshot-1.png` | 1912x1205 | 9 | `x=0.0, y=0.20, w=0.16, h=0.50` |
| `tests/ru/screenshot-2.png` | 2559x1599 | 6 | `x=0.0, y=0.20, w=0.16, h=0.50` |

Both are Russian Set 18 (Enchanted Wilds) trait panels on a dark,
translucent background. Expected pairs live under the `traits` object in
`tests/ru/screenshot-N.json`; the file's `progress` and `players` data is
not used for recognition comparison.

## Method

Each run cropped the panel, applied one preprocessing mode, ran
PaddleOCR on the crop, and compared detected label/count pairs against
the expected pairs. A row counted as matched only when a numeric line
sat immediately left of a label line on the same vertical band. This
mirrors the parser's geometry rules.

Reported as `matched / expected`. "Labels" means lines containing at
least one letter; "counts" means lines matching `^\d{1,2}$`.

## Preprocessing comparison

Identity / CLAHE variants, default detection thresholds:

| Mode | screenshot-1 | screenshot-2 | Notes |
| --- | --- | --- | --- |
| `raw` | partial | partial | Missed thin `1` counts |
| `upscale2x` | 9/9 | 3/9 | Counts missed on the larger panel |
| `upscale2x_gray_clahe` | 8/9 | 6/6 | One `1` lost on screenshot-1 |
| `upscale3x_gray_clahe` | 9/9 | 6/6 | All counts; `Дух леса` misread as `Duх лesa` |
| `upscale3x_adaptive` | 9/9 | 6/6 | All counts and all labels |
| `threshold` (Otsu) | poor | poor | Label fragments split apart |

Adaptive threshold parameter sweep at 3x:

| Block size | C | screenshot-1 | screenshot-2 |
| --- | --- | --- | --- |
| 21 | 8 | 10/9 | false positives |
| 31 | 10 | 9/9 | 6/6 |
| 41 | 12 | 10/9 | false positives |

`blockSize=21` and `blockSize=41` introduced extra junk rows. `31/10`
was the only setting that was correct on both fixtures without false
positives.

At 2x the same adaptive settings underperformed (screenshot-1 dropped to
3/9 or 4/9), which is why 3x is the default.

## Chosen default

`upscale3x_adaptive`:

1.  Upscale the crop 3x with cubic interpolation.
2.  Convert to grayscale.
3.  Apply `cv2.adaptiveThreshold` with
    `ADAPTIVE_THRESH_GAUSSIAN_C`, `THRESH_BINARY`, `blockSize=31`,
    `C=10`.

This recovered the thin `1` glyphs that raw and 2x modes missed, and it
was the only mode that read `Дух леса` correctly on screenshot-2.

## Confidence floors

With adaptive thresholding, detection occasionally emits a junk glyph
(a lone `B`, `X`, or similar) at low confidence. Before a hard floor was
added, those glyphs became phantom trait rows and forced `partial` even
when every real trait was correct.

Observed confidences:

-   Junk glyphs: 0.18-0.47.
-   Lowest real label/count on the fixtures: 0.62.

Chosen floor: `min_ocr_confidence = 0.5` (drop before parsing).
Row warning threshold stays at `min_confidence = 0.6`.

## Final results

Command:

```powershell
cd apps/recognition
.\.venv312\Scripts\python.exe -m tft_recognition.cli `
  --fixture ..\..\tests\ru\screenshot-1.fixture.json `
  --pretty --out result.json
```

| Fixture | Rows | Status | Comparison | Approx. elapsed |
| --- | --- | --- | --- | --- |
| `screenshot-1` | 9/9 | `ok` | passed | ~42 s |
| `screenshot-2` | 6/6 | `ok` | passed | ~88 s |

Elapsed times are wall-clock for one CLI run, including model load on the
first invocation in a fresh process. They are not a throughput target.

## Observed failure modes

-   **Thin glyphs.** Single-pixel-wide `1` counts disappear at 1x and
    often at 2x. This drove the 3x default.
-   **Merged words.** OCR sometimes drops the space in
    `Крепкая связь` -> `Крепкаясвязь`. Resolution is fuzzy matching with
    a recorded `method: "fuzzy"`, not a special case.
-   **Compact breakpoints.** Breakpoint sublines can come back as
    `246` or `3>57` instead of `2 > 4 > 6`. These are numeric but are not
    counts; the parser reclassifies them by position and keeps them as
    diagnostics.
-   **Junk glyphs.** Low-confidence artifacts become phantom rows unless
    dropped by the OCR floor.
-   **MKLDNN crash.** With oneDNN enabled, PaddlePaddle 3.3 fails on
    Windows during inference. Disabled by default.
-   **Model download on first run.** The first run downloads
    `PP-OCRv5_server_det` and `eslav_PP-OCRv5_mobile_rec` into the
    PaddleX cache, which inflates first-run time.

## Reproduction

```powershell
cd apps/recognition

# Core tests (fake OCR, no PaddleOCR needed)
.\.venv\Scripts\python.exe -m pytest -q

# Full suite including real OCR on both fixtures
.\.venv312\Scripts\python.exe -m pytest -q

# Real OCR only
.\.venv312\Scripts\python.exe -m pytest -m ocr -q

# CLI on each fixture
.\.venv312\Scripts\python.exe -m tft_recognition.cli `
  --fixture ..\..\tests\ru\screenshot-1.fixture.json --fail-on-mismatch
.\.venv312\Scripts\python.exe -m tft_recognition.cli `
  --fixture ..\..\tests\ru\screenshot-2.fixture.json --fail-on-mismatch
```

## Caveats

-   Two fixtures only. Do not treat the numbers as general OCR accuracy.
-   The Set 18 catalog is fixture data; see `DECISIONS.md`.
-   Re-benchmark before changing UI scale, language, or resolution, and
    before lowering the confidence floors.
