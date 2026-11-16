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

-   The three tracked screenshots in `tests/ru/` are Russian TFT **Set 18 /
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
-   Each fixture stores its own crop in its manifest. The tracked fixtures
    currently share `{x: 0.0, y: 0.20, width: 0.16, height: 0.50}`.

Reason: normalized coordinates survive different resolutions
(`1912x1205`, `2559x1599`, and `2560x1600` here) and match the future
calibration UI, which will draw a rectangle over a preview rather than
store pixels.

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
    name/count pairs plus an `ok` status on the tracked fixtures.
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
-   **Screenshot retention and licensing.** The tracked screenshots under
    `tests/ru/` are tracked. Their redistribution terms are unverified.
    Do not move, delete, or publish them without confirmation.
-   **Threshold generalization.** The 0.5 OCR floor and 3x adaptive
    preprocessing are tuned to the tracked panels. Re-benchmark before
    supporting other UI scales, languages, or resolutions.
-   **Breakpoint mapping.** Parsed breakpoint text is diagnostic only. It
    is not yet connected to catalog breakpoint metadata or composition.
-   **Temporal validation.** Deferred to the desktop worker; the POC
    publishes a reading per image with no smoothing.

## 13. Desktop foundation (Milestones 0 and 1)

Decided:

-   **Build tooling.** `electron-vite` builds the main, preload, and
    renderer bundles. Vue 3 with `<script setup>`, TypeScript, and Pinia.
    Navigation is a small store-driven view switch, not a router; the app
    has four fixed screens and no deep-linking requirement yet.
-   **Workspace shape.** A pnpm workspace with `apps/desktop`,
    `apps/recognition`, and `packages/shared-types`. Only contracts are
    shared with TypeScript today; no UI or recognition logic is duplicated
    across packages.
-   **Contracts.** Zod schemas in `packages/shared-types` are the source
    of truth for IPC payloads, the worker protocol, capture requests and
    results, settings, and recognition results. Types are inferred from
    schemas so runtime validation and compile-time types cannot drift.
-   **Worker transport.** Newline-delimited JSON over stdio. No local
    port, no HTTP, no WebSocket. The desktop process owns the child, so
    there is no listener to secure and no port to collide with.
-   **Worker lifecycle.** The main process starts, stops, and restarts
    the worker, tracks
    `stopped → starting → running → stopping → stopped`, and exposes
    `error` (spawn failure or startup timeout) and `disconnected`
    (unexpected exit or missed heartbeat). The UI shows the same state
    machine and a visible disconnect.
-   **Heartbeats.** The worker emits periodic heartbeats; the supervisor
    also sends pings and records `lastHeartbeatAt` and `lastPongAt`. A
    timeout beyond `heartbeatTimeoutMs` marks the worker disconnected and
    terminates it. Timeout must exceed the interval.
-   **Settings.** Validated JSON in the Electron `userData` directory,
    not SQLite. Missing fields are merged with defaults; a corrupt file
    is backed up and replaced with defaults and the problem is logged.
    A database is deferred until settings or composition history outgrow
    a single document.
-   **Capture.** `desktopCapturer` in the main process, `getDisplayMedia`
    in the renderer via the preload bridge, canvas PNG encoding in the
    renderer, and validated file writes in the main process. Permission
    for `display-capture` is granted only to the trusted main window.
-   **Capture source selection.** The main process resolves the selected
    source itself when answering `setDisplayMediaRequestHandler`; the
    renderer never supplies a source object back to the main process.
-   **Display metadata.** Screen sources are joined to
    `screen.getAllDisplays()` to expose scale factor and derived physical
    size. Windows can report an empty `display_id`, so the join falls back
    to the source id and then the source index. Details and limits are in
    `docs/CAPTURE_SPIKE.md`.
-   **Library boundaries.** Vue components render state and call Pinia
    stores. Stores orchestrate IPC. Recognition, capture geometry, and
    future rule/audio logic stay in packages, not in `.vue` files.
-   **Naming and data location.** The app name is
    `TFT Soundtrack Companion`; `userData` is
    `%APPDATA%\TFT Soundtrack Companion`.
-   **Python environment discovery.** An explicit `pythonPath` from
    settings wins; otherwise the app probes
    `apps/recognition/.venv312`, then `.venv`, then `python` on `PATH`.
    The real OCR environment is 3.12 because PaddlePaddle 3.3 has no
    wheel for 3.14.
-   **Worker stub.** The Milestone 1 worker is a standard-library-only
    stdio server. It announces `worker.ready`, heartbeats, answers
    `worker.ping`, reports protocol errors without exiting, and shuts down
    on `worker.shutdown`. It imports no OCR dependency so startup stays
    fast and testable.
-   **Verification modes.** `smoke` launches the built app, confirms the
    renderer mounted, and cycles the worker. `smoke:capture` runs the
    real capture path and saves a PNG. Both are non-interactive
    diagnostics, not substitutes for the manual checklist.

Reason: this slice had to prove process boundaries and failure
visibility before recognition or audio exists. stdio and a supervised
child keep that boundary explicit and testable, and keeping writes in the
main process means the renderer never gains filesystem authority.

Consequence: the renderer is trusted for capture but not for file paths
or source selection. Worker messages are versioned (`schemaVersion: 1`)
and validated with Zod on both sides, so adding OCR messages is an
additive change or an explicit version bump.

## 14. Open questions after the foundation slice

Open, recorded so they are not mistaken for settled:

-   **Packaging.** No installer or code signing yet. Decide the electron
    builder configuration, auto-update policy, and whether the Python
    runtime ships with the app or is resolved from a user-managed
    environment. Revisit after Milestones 5–6 (section 15.5).
-   **Python distribution.** Requiring users to create a venv is fine for
    development. Shipping OCR needs a bundled runtime or a guided setup,
    and PaddleOCR model size affects installer size. Revisit after
    Milestones 5–6 (section 15.5).
-   **Capture ownership.** Capture currently runs through the renderer.
    If recognition needs higher or steadier frame rates, decide whether
    frames move directly into the worker, whether the worker captures, or
    whether the main process keeps a frame buffer.
-   **Frame transport.** PNG over IPC is fine for a spike. The intended
    recognition cadence is 0.33–1 fps (section 15.3), so a path-based
    handoff to the worker is likely sufficient. Measure before choosing a
    shared buffer or compressed stream.
-   **Multi-monitor and mixed DPI.** The display join and the physical
    size derivation need verification on multi-monitor and mixed-scale
    setups. Exhaustive testing is deferred to MVP validation
    (section 15.1).
-   **Settings migration.** The settings document has a schema but no
    migration history. Define how old documents upgrade once fields
    become load-bearing.
-   **Worker protocol growth.** `schemaVersion: 1` covers lifecycle only.
    Adding capture, calibration, and recognition messages may need
    capability negotiation rather than a version bump per feature.
-   **Audio host.** Web Audio in the renderer is the plan, but the
    process that owns the persistent timeline and the rule engine is not
    settled. Keep both out of components regardless.
-   **Log retention.** The desktop log is append-only NDJSON in
    `logs\main.log` that rolls over once at 5 MB to `main.log.1`. Decide
    whether one backup and a size cap are enough for long sessions or
    whether time-based retention is needed.

## 15. MVP risk posture

Recorded after the desktop foundation slice. These are operating
assumptions for the MVP, not permanent commitments. Each item names the
stage where it is revisited.

### 15.1 OCR across resolutions and DPI

-   Exhaustive resolution and scaling tests are deferred to MVP
    validation. The owner will test the common variants and fix defects
    then.
-   Until that happens, recognition must stay resolution-independent:
    normalized crops, capture metadata (frame size, display scale factor,
    physical size) carried with every request, preprocessing mode
    configurable, and no hardcoded pixel geometry in the parser or
    protocol.
-   Adding a resolution profile must not require changing the parser, the
    protocol, or the UI.
-   Do not treat one verified display as evidence that other scales work.

### 15.2 Set catalogs

-   The MVP targets **Set 18, Russian locale only**.
-   Additional sets are added after the MVP. The pipeline therefore takes
    a `setId` and a catalog reference; set-specific data stays out of
    code.
-   The illustrative fixture catalog is sufficient to prove the
    recognition plumbing in Milestone 2.
-   Authoritative trait statistics (internal IDs, Russian display names,
    aliases, breakpoints) are needed by the rule engine in Milestone 4,
    and before recognized names can be presented as trustworthy.
-   Never ship the fixture catalog as if it were authoritative.

### 15.3 Recognition cadence

-   Debug target: about 1 frame per second.
-   Production target: one frame every 2–3 seconds (0.33–0.5 fps).
-   Music does not need to react instantly. Correctness and stability
    matter more than latency.
-   Temporal validation must be **time-based**, not “N consecutive
    frames”, because cadence is configurable and may be below 1 fps.
-   Keep at most one analysis in flight and drop stale frames instead of
    queueing them.
-   The current settings schema stores an integer `frameRate` with a
    minimum of 1. Replace it with an interval (for example
    `captureIntervalMs`) or allow fractional rates when the live loop is
    built.

### 15.4 Fullscreen capture

-   Exclusive-fullscreen window capture is untested. Test it once the
    recognition loop exists and there is something meaningful to verify.

### 15.5 Audio rights and packaging

-   Deferred. Revisit after the music engine and end-to-end integration
    (Milestones 5–6): licensed audio sources, redistribution terms,
    bundled Python/OCR runtime, installer size, and code signing.

### 15.6 Extensibility guardrails

These keep the deferred risks cheap to address later:

-   Crops are normalized fractions, never stored pixels.
-   Every capture request carries its source dimensions and DPI metadata
    so a future profile can be added without replaying old assumptions.
-   The OCR engine stays behind the `OcrEngine` adapter.
-   Catalog selection is data, addressed by id or path.
-   The worker protocol is versioned and additive where possible.
-   Recognition is stateless per request; cadence and debounce live in
    the desktop, not in the recognizer.

## 16. Recognition request path (Milestone 2a)

Decided:

-   **Request contract.** The renderer calls
    `window.tft.recognition.analyze` with `filePath`, `captureTimestamp`,
    `crop`, and optional `setId`/thresholds. The main process validates
    the payload with the shared Zod schema, resolves the catalog, and
    sends `recognition.analyze` to the worker with a generated
    `requestId`.
-   **Filesystem authority.** The renderer names only a file inside the
    configured capture directory. The main process rejects any resolved
    path outside it and any missing file before the worker is involved.
-   **Catalog resolution.** The main process prefers
    `apps/recognition/data/sets/<setId>-ru.json`, then falls back to
    `apps/recognition/tests/fixtures/catalog/<setId>-ru.fixture.json`.
    Set ids are restricted to a safe slug pattern; the renderer cannot
    supply a catalog path. Set 18 is the only MVP set (section 15.2).
-   **Correlation.** Worker results extend the existing result with
    `requestId`; correlated `worker.error` messages also carry it. The
    supervisor keeps a pending-request map, resolves or rejects the
    matching promise, rejects everything on exit/dispose, and logs
    unmatched results.
-   **Serialization.** The worker runs one analysis at a time on its
    stdin loop. A second request is rejected as busy rather than queued.
    Importing NumPy from a helper thread while the main thread blocks on
    stdin deadlocks on Windows; this is an empirical constraint, not a
    preference. Heartbeats still run on their own thread.
-   **Timeout and liveness.** The supervisor allows 300 s per analysis
    and kills the child on timeout so a stuck OCR call cannot block the
    worker forever. While a request is in flight it skips the heartbeat
    age check, because PaddleOCR can hold the GIL and starve the
    heartbeat thread. A completed response refreshes the heartbeat clock.
-   **Boot race.** `ensureRunning()` starts the worker if needed and
    waits for `worker.ready`, so the first click works even when
    auto-start is still in its handshake.
-   **UI.** The capture screen owns editable normalized crop fields, an
    Analyze button for the last saved PNG, and a result view with
    normalized traits, match method/score, unknown rows, and
    diagnostics. The store owns the request; the component only renders.
-   **Verification.** `smoke:recognition` copies the tracked Set 18
    screenshot into the capture directory, calls the renderer bridge,
    and asserts a correlated result before deleting the temporary file.
    The Python worker tests cover fake-OCR analysis, invalid requests,
    correlated errors, and liveness after errors.

Reason: this is the smallest end-to-end slice that proves the renderer,
preload, IPC, supervisor, and Python pipeline agree on one versioned
contract without giving the renderer filesystem authority.

Consequence: cold PaddleOCR analysis measured about **73 s** for the
1912x1205 fixture and about **128 s** for the 2560x1600 fixture on the
reference machine (MKLDNN disabled). The larger pixel crop is the main
cost: the same normalized rectangle becomes 410x800 instead of 306x603.
That is far below the 0.33–0.5 fps production cadence in section 15.3.
Before the live loop is built, reduce inference time (candidate levers: a
lighter detector or recognizer model, a fixed OCR input size instead of
3x upscaling, revisiting MKLDNN on this Paddle build, or warm-up plus
reuse). Do not assume the current latency is acceptable for continuous
capture. The current UI analyzes one saved capture at a time; crop
persistence and the live loop remain open.
