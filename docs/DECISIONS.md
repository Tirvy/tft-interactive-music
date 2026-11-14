# Decisions: trait-panel recognition POC

This document records decisions made while building the Python
recognition proof of concept under `apps/recognition`. It separates
settled choices from open questions so later implementation work does not
silently inherit an assumption.

The POC is intentionally narrow. It answers one question: can a
screenshot of the visible trait panel be turned into reliable
`trait name -> displayed count` rows with traceable raw OCR data? It does
not implement live capture, calibration UI, temporal validation, the rule
engine, or audio playback.

## 1. Scope of the POC

Decided:

-   Recognition only. The POC starts from an image file, not a live game
    window.
-   The only recognition source is the visible trait panel: trait name
    and displayed count.
-   No board-unit, bench, or champion-portrait recognition, and no
    champion-to-trait inference.
-   Capture/calibration, OCR/row parsing, normalization, composition,
    rules, and audio stay separate modules.
-   The POC must not depend on a live TFT match.

Reason: these are the non-negotiable product boundaries in
`AI_CODING_GUIDE.md` and `ARCHITECTURE.md`. Keeping the POC file-based
makes parsing and normalization testable without a running game.

## 2. Fixture set is Set 18, not Set 10

Decided:

-   The two tracked screenshots in `tests/ru/` are Russian TFT **Set 18 /
    Enchanted Wilds** panels.
-   The POC catalog targets Set 18 even though the planning documents use
    Set 10 / Remix Rumble as the inspiration and example.

Reason: the visible trait names in the fixtures (`Древний лес`,
`Крепкая связь`, `Инферно`, `Страж`, `Заводила`, `Джаггернаут`,
`Заклинатель`, `Коварная флора`, `Адаптация`, `Опустошитель`, `Фея`,
`Дух леса`) match Set 18, not Set 10. Building a Set 10 catalog would
make the only available fixtures fail.

Consequence: `AI_CODING_GUIDE.md` still describes Set 10. That mismatch is
recorded in section 12 and should be reconciled in the product docs
before the next set work.

## 3. Fixture catalog is illustrative, not authoritative

Decided:

-   `tests/fixtures/catalog/set-18-ru.fixture.json` is fixture data.
-   It uses likely Set 18 internal trait IDs (`Adaptor`, `Attuned`,
    `OldGrowth`, `Inferno`, `Defender`, `Rapidfire`, `Juggernaut`,
    `Spellweaver`, `FloraFatalis`, `Ravager`, `Fae`, `Elderwood`).
-   The catalog carries a `fixture-1` data version and a note that it must
    be replaced with an authoritative source.

Reason: Set 18 names were cross-checked against a secondary community
source (OP.GG Russian synergy list), which is good enough to exercise the
pipeline but not good enough to ship. Internal IDs and breakpoints are
plausible, not verified.

Consequence: recognition reaching `ok` against this catalog proves the
pipeline works; it does not prove the data is correct or current.

## 4. Crop geometry

Decided:

-   Crops are expressed as normalized `x, y, width, height` fractions of
    the source image, not absolute pixels.
-   Every crop is validated against `[0, 1]` bounds, non-zero size, and
    the actual source dimensions before OCR runs.
-   Each fixture stores its own crop in its manifest. The two fixtures
    currently share `{x: 0.0, y: 0.20, width: 0.16, height: 0.50}`.

Reason: normalized coordinates survive different resolutions
(`1912x1205` and `2559x1599` here) and match the future calibration UI,
which will draw a rectangle over a preview rather than store pixels.

Consequence: absolute pixel diagnostics are still emitted, but only as
derived values. Callers never supply pixel crops.

## 5. Displayed count vs breakpoint subline

Decided:

-   The displayed count is the standalone numeric line that sits
    immediately left of the label and shares its vertical band.
-   Breakpoint sublines such as `2 > 3 > 5 > 7`, `2>4>6`, `1/2`, or a
    compact OCR run like `246` are preserved as diagnostics only. They are
    never used as the displayed count.
-   Counts must match `^\d{1,2}$`. Anything longer or containing
    separators is not a count.
-   When several numeric lines can be a count, the nearest one to the
    left of the label wins; the others are recorded as ignored lines.

Reason: the TFT panel shows a count (current units) plus a separate
breakpoint track. Conflating them would produce wrong rule inputs. The
number sits left of the label, while breakpoints sit below it, so
geometry is a reliable discriminator.

Consequence: breakpoint text is not yet mapped to catalog breakpoint
metadata. That mapping is future composition work.

## 6. OCR confidence floors

Decided:

-   `min_ocr_confidence = 0.5` is a hard floor. Lines below it are
    discarded before parsing and recorded as `low_ocr_confidence`.
-   `min_confidence = 0.6` is a row-level warning threshold. Rows below it
    are kept but mark the result `partial`.
-   Both are configurable through `PipelineConfig` and the CLI.

Reason: adaptive thresholding occasionally emits a junk glyph such as a
lone `B` or `X` at 0.18-0.47 confidence. Those glyphs became phantom
trait rows and forced `partial` even when every real trait was correct.
The lowest real label observed was 0.62, so 0.5 separates cleanly on the
fixtures.

Consequence: a genuinely faint real trait below 0.5 would be dropped
rather than surfaced as unknown. When more fixtures exist, revisit the
floor or make it adaptive.

## 7. Preprocessing default

Decided:

-   Default mode is `upscale3x_adaptive`: 3x cubic upscale, then a
    Gaussian adaptive threshold (`blockSize=31`, `C=10`).
-   Other modes remain available for benchmarking:
    `raw`, `upscale2x`, `upscale3x`, `gray`, `gray_clahe`,
    `upscale2x_gray_clahe`, `upscale3x_gray_clahe`, `threshold`.
-   OCR engines report boxes in the coordinate space of the image they
    receive, so the pipeline divides boxes by the mode's scale before
    parsing.

Reason: the dark, translucent panel hides thin `1` glyphs. Raw OCR
missed them; 3x adaptive threshold recovered every count and label on
both fixtures. See `OCR_BENCHMARK.md` for the comparisons.

Consequence: this is tuned to two panels. A different UI scale, font, or
background may need a different mode. The mode is a setting, not a
hardcoded assumption.

## 8. Trait normalization

Decided:

-   Exact catalog match is tried first.
-   Aliases are used only when a catalog entry defines them.
-   Fuzzy matching uses stdlib `difflib.SequenceMatcher` with a minimum
    score of `0.85` and a minimum score margin of `0.08` over the next
    best candidate.
-   Unknown or ambiguous labels are never silently mapped. They become
    unknown rows with a best-candidate hint and force `partial`.
-   Fuzzy matches record `method: "fuzzy"` and their score so callers can
    audit them.

Reason: OCR sometimes drops spaces (`Крепкаясвязь`), which exact matching
cannot handle. Fuzzy matching fixes that while the margin rule prevents
mapping two similar trait names to the same catalog entry.

Consequence: fuzzy matching is conservative by design. If it rejects a
real label, the correct fix is an alias in the catalog, not a lower
threshold.

## 9. Result status rules

Decided:

-   `ok`: at least one trait row parsed, no unknown rows, no
    low-confidence warnings.
-   `partial`: at least one row parsed, but some rows are unknown,
    ambiguous, duplicated, or below the warning threshold.
-   `unavailable`: no trait rows parsed.
-   `error`: the OCR adapter raised an error.

Reason: downstream composition needs a single explicit verdict. A
silent `ok` with dropped rows would let the soundtrack react to a wrong
composition.

Consequence: the POC does not add temporal stability. A future worker
should require repeated consistent readings before publishing a
composition.

## 10. OCR adapter and PaddleOCR runtime

Decided:

-   OCR sits behind an `OcrEngine` adapter contract.
-   PaddleOCR is the first real adapter; a deterministic fake adapter
    powers hermetic tests.
-   PaddleOCR is imported lazily so core tests run without it.
-   PaddleOCR results normalize both v2-style nested lists and v3-style
    `rec_texts`/`rec_scores`/`rec_polys` mappings.
-   PaddleX MKLDNN/oneDNN is disabled by default via
    `PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=False`, set at module import
    before any `paddleocr` import.

Reason: PaddlePaddle 3.3 on Windows fails inside oneDNN with
`ConvertPirAttribute2RuntimeAttribute not support
[pir::ArrayAttribute<pir::DoubleAttribute>]`. The plain CPU path works.
PaddleOCR rejects the equivalent `run_mode="paddle"` constructor
argument, so the environment flag is the supported lever.

Consequence: a process that imports `paddleocr` before this package may
read the flag too late. In-process callers should import
`tft_recognition.ocr.paddle` first, as the CLI and tests do.
`--paddle-enable-mkldnn` opts back in for machines where it works.

## 11. Testing and fixture handling

Decided:

-   Core unit tests are hermetic and use `FakeOcrEngine`.
-   Real PaddleOCR tests are marked `ocr` and assert the exact expected
    name/count pairs plus an `ok` status on both fixtures.
-   Existing fixtures must not be deleted or rewritten without
    confirmation. The sidecar `*.fixture.json` manifests were added next
    to the original `screenshot-N.json` files without touching them.
-   Debug screenshots and preprocessed crops are not retained by default.
    `--debug-dir` is an explicit opt-in.

Reason: keeps the test suite fast and deterministic while still
verifying real OCR on the tracked screenshots. Preserves user-provided
artifacts.

## 12. Unresolved questions

Open, recorded so they are not mistaken for settled:

-   **Authoritative catalog.** Set 18 internal IDs, Russian display
    names, aliases, and breakpoints need a verified Riot-aligned source
    before shipping.
-   **Set mismatch in product docs.** `AI_CODING_GUIDE.md` and
    `ARCHITECTURE.md` describe Set 10. Decide whether the product targets
    the current set dynamically, or pins a set per release.
-   **Screenshot retention and licensing.** The two screenshots under
    `tests/ru/` are tracked. Their redistribution terms are unverified.
    Do not move, delete, or publish them without confirmation.
-   **Threshold generalization.** The 0.5 OCR floor and 3x adaptive
    preprocessing are tuned to two panels. Re-benchmark before supporting
    other UI scales, languages, or resolutions.
-   **Breakpoint mapping.** Parsed breakpoint text is diagnostic only. It
    is not yet connected to catalog breakpoint metadata or composition.
-   **Temporal validation.** Deferred to the desktop worker; the POC
    publishes a reading per image with no smoothing.
