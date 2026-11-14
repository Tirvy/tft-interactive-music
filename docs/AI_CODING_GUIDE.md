# AI Coding Guide

This document gives coding assistants project context and implementation
constraints. Read this before modifying the codebase.

## Project summary

Build a local desktop companion for Teamfight Tactics. It reads trait
names and displayed counts from the visible trait panel on the left
side of the TFT UI, normalizes those values, evaluates user-defined
music rules, and controls a layered soundtrack.

The application is inspired by TFT Set 10 / Remix Rumble's dynamic music
concept. It should be architected to support multiple sets through data
packs.

## Non-negotiable product decisions

-   Recognition is based on the visible trait panel, not champion
    portraits.
-   Do not implement board-unit or bench champion recognition.
-   Do not infer traits from champions.
-   The recognized source of truth is the trait name and count displayed
    in the TFT UI.
-   Music behavior is layered playback, not only whole-song switching.
-   Music layers should remain synchronized.
-   Composition changes should adjust gains and should not restart
    unaffected audio layers.
-   Local audio files are the initial music source.
-   The core should support multiple TFT sets, even if the first curated
    data pack is Set 10.
-   The app is a soundtrack companion, not a tactical or competitive
    gameplay assistant.

## Proposed technology

-   Electron desktop shell.
-   Vue 3 + TypeScript renderer.
-   Pinia for UI state.
-   Python recognition worker.
-   OpenCV for crop/image preprocessing.
-   PaddleOCR as an initial OCR candidate, behind an adapter.
-   Local WebSocket or Electron IPC for worker communication.
-   TypeScript composition engine and rule engine.
-   Web Audio API for mixing and transitions.
-   SQLite for user configuration.
-   Versioned JSON for static set catalogs.

Do not add a framework or service without explaining why it is needed.
Prefer the simplest solution that preserves the architecture.

## Required engineering boundaries

Keep these concerns separate:

1.  Capture and calibration.
2.  OCR and row parsing.
3.  Trait normalization against a set catalog.
4.  Temporal validation and stable composition state.
5.  Pure composition/rule evaluation.
6.  Audio playback and mixing.
7.  UI and persistence.

Do not put OCR logic in Vue components. Do not put trait-specific rules
in the audio engine. Do not make the rule engine depend on Electron,
Python, or browser UI state.

## Data contracts

Use shared, versioned types and runtime validation for
messages/configuration.

A normalized composition should contain: - `setId` - trait IDs -
displayed counts - optional confidence - optional derived active/next
breakpoint - status (`stable`, `partial`, `stale`, or `unavailable`) -
capture timestamp - revision

A recognition result should preserve raw OCR text and unknown rows for
diagnostics. Never silently discard unknown traits.

A desired mix should contain: - music pack ID - target gain per layer -
matched rule IDs - generation timestamp

Keep `count` distinct from `activeBreakpoint`. The count is recognized
from the UI; breakpoint metadata is derived from the selected set
catalog.

## Recognition behavior

-   Use a user-calibrated crop rectangle stored as normalized
    coordinates.
-   Do not hardcode absolute screen coordinates.
-   Validate crop bounds and source dimensions.
-   Keep the OCR implementation behind an adapter.
-   Use exact catalog matching first.
-   Use aliases only when defined in the catalog.
-   Use fuzzy matching conservatively and require a confidence margin.
-   Preserve unknown/ambiguous rows for diagnostics.
-   Require repeated consistent readings before applying a new
    composition.
-   Preserve the last-known-good composition during brief failures, but
    expose stale status.
-   Make capture rate and validation thresholds configurable.

## Music behavior

-   Keep a persistent playback timeline.
-   Do not restart all audio when a trait changes.
-   Wait until there was at least 3 seconds without trait changes to change music.
-   If OCR fails or gives unrecognised data - keep last chosen soundtrack.
-   Use gain ramps for smooth transitions.
-   Support immediate and next-bar transitions.
-   Only use next-bar timing when BPM, meter, offsets, and loop metadata
    are valid.
-   Fall back to a smooth immediate transition when timing data is
    incomplete.
-   Clamp gains to the supported range.
-   Report missing files and decoding errors.
-   Keep raw Web Audio nodes encapsulated inside the music-engine
    package.

## Rule behavior

MVP conditions: - Trait present. - Trait count comparison. - Trait
breakpoint. - Nested `all`, `any`, and `not`.

Rules may activate multiple different layers simultaneously. If multiple
rules control the same layer, use documented deterministic conflict
resolution. Do not let rule iteration order determine the result.

The rule engine should be pure and deterministic:
`evaluate(composition, rules) -> desiredMix + matchedRuleDiagnostics`.

## UI requirements

Build these screens incrementally: - Now Playing. - Capture source and
panel calibration. - Music Studio. - Rule Editor. - Composition
Simulator.

The simulator is important: developers and users must be able to test
compositions and rules without launching TFT.

Show recognition status, confidence/unknown warnings, last successful
capture, matched rules, and active layers. Do not hide uncertainty.

## Quality requirements

-   TypeScript strict mode.
-   Runtime validation at external boundaries.
-   Unit tests for composition and rule packages.
-   Fixture-based tests for OCR parsing and normalization.
-   Tests for audio transitions and synchronization.
-   Clear errors and structured local logs.
-   No silent fallback from unknown trait to a guessed trait.
-   No unnecessary network dependency at runtime.
-   Do not retain gameplay screenshots by default.

## Policy and content constraints

The app reads visible trait names/counts only to select music. Do not
add tactical recommendations, opponent scouting, or competitive
analysis. Do not read or modify game memory, inject into the game, or
alter game files. Before public distribution, review current Riot
policies and any applicable registration requirements. Do not bundle
copyrighted music or game assets unless the project has permission to
distribute them.

## Working method for coding assistants

Before coding: 1. Inspect the existing repository and identify what is
already implemented. 2. Read this guide and the
architecture/implementation documents. 3. Summarize the relevant
existing structure and propose a small implementation plan. 4. Identify
assumptions and verify them against the codebase. 5. Avoid replacing
working infrastructure without a concrete reason.

While coding: 1. Implement one milestone or cohesive vertical slice at a
time. 2. Define or update types and schemas before wiring UI. 3. Keep
modules small and responsibilities explicit. 4. Add tests alongside
behavior. 5. Run relevant tests, type checks, and linting. 6. Do not
claim tests passed unless they were actually run. 7. Update
documentation when contracts or decisions change.

When uncertain: - Prefer a small prototype over speculative
abstraction. - Ask before making product decisions that materially
change scope. - Do not invent TFT trait data. Use a verified data source
or mark fixtures as illustrative. - Do not assume the OCR library will
work until tested on real screenshots. - Record unresolved decisions in
a `docs/DECISIONS.md` file.

## First coding task

Start with a recognition proof of concept, not the full desktop app:

1.  Create a Python script that loads a screenshot from disk.
2.  Apply a configurable crop rectangle.
3.  Run the selected OCR engine.
4.  Parse visible rows into raw label/count pairs.
5.  Normalize labels against a small fixture trait catalog.
6.  Print structured JSON containing trait IDs, counts, confidence,
    unknown rows, and diagnostics.
7.  Add fixture-based tests for parsing and normalization.
8.  Document the OCR accuracy and failure cases observed.

Keep this proof of concept independent from live TFT capture. Once it
works on representative screenshots, connect it to the desktop capture
pipeline.
