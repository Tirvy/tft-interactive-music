# Architecture: TFT Soundtrack Companion

## 1. System overview

The application has four major subsystems:

1.  **Capture and recognition**: obtains screenshots and reads the
    visible trait panel.
2.  **Composition model**: converts recognized rows into a normalized
    trait state.
3.  **Rule engine**: determines which audio layers should be active and
    at what gain.
4.  **Audio engine**: plays synchronized stems and applies smooth,
    optionally beat-aligned transitions.

The UI configures the system, displays recognition status, edits music
packs and rules, and provides manual test controls.

``` mermaid
flowchart TD
    A[TFT game window] --> B[Electron capture]
    B --> C[Calibrated trait-panel crop]
    C --> D[Python recognition worker]
    D --> E[OCR + trait normalization]
    E --> F[Temporal validation]
    F --> G[Normalized composition]
    G --> H[TypeScript rule engine]
    H --> I[Desired audio mix]
    I --> J[Web Audio music engine]
    J --> K[Audio output]
    L[Vue UI] --> M[Settings and calibration]
    L --> N[Music packs and rules]
    M --> B
    N --> H
    N --> J
    G --> L
```

## 2. Architectural principles

-   **Trait-panel-first**: recognition is based on the trait names and
    counts displayed by TFT, not champion portraits or board-unit
    detection.
-   **Set-independent core**: the recognition pipeline and music engine
    must not contain hardcoded set-specific trait logic.
-   **Data-driven game sets**: trait IDs, display names, aliases, and
    optional breakpoint metadata live in versioned set catalogs.
-   **Recognition is fallible**: uncertain or missing OCR must not cause
    arbitrary soundtrack changes.
-   **Audio playback is persistent**: composition updates change layer
    gains; they should not restart every audio source.
-   **Local-first**: recognition, rules, and playback should work
    locally.
-   **Testable boundaries**: every subsystem has explicit input/output
    contracts and can be tested with fixtures or simulated compositions.

## 3. Desktop application

### Electron main process

Responsibilities: - Application lifecycle and window management. -
Selecting and capturing the TFT window or screen source. - Starting,
monitoring, and stopping the Python recognition worker. - Managing local
IPC/WebSocket connection details. - Persisting app-level settings and
handling file access permissions.

Do not put OCR, trait matching, or audio-rule logic in the Electron main
process.

### Vue renderer

Responsibilities: - Now Playing dashboard. - Recognition status and
detected-trait list. - Capture-source selection and panel calibration
UI. - Music pack editor. - Rule editor. - Manual composition
simulator. - Audio mixer and master volume controls.

Use Pinia for UI state. Keep business logic in packages rather than
large Vue components.

## 4. Recognition subsystem

### 4.1 Capture

Capture the selected TFT window or display. The initial implementation
may use Electron's desktop capture facilities and pass frames to the
Python worker. Avoid capturing more frequently than needed.

Suggested initial target: 2--4 frames per second. Treat this as a
tunable starting point, not a hard requirement.

### 4.2 Panel calibration

The user selects a rectangle around the visible trait list. Store the
rectangle relative to the captured source dimensions:

``` ts
interface NormalizedRect {
  x: number;      // 0..1 relative to source width
  y: number;      // 0..1 relative to source height
  width: number;  // 0..1
  height: number; // 0..1
}
```

Normalized coordinates allow the crop to scale when the captured window
dimensions change. If the aspect ratio or layout changes materially,
request recalibration rather than silently using a bad crop.

Calibration UI requirements: - Show a screenshot preview. - Allow the
user to draw and adjust the crop rectangle. - Show the resulting crop
preview. - Save and reload the rectangle. - Provide a clear
recalibration action. - Detect obviously invalid or out-of-bounds
rectangles.

Do not assume the trait panel always occupies a fixed absolute pixel
location.

### 4.3 OCR pipeline

Suggested processing stages:

1.  Receive frame.
2.  Apply calibrated crop.
3.  Preprocess image if needed: resize, contrast adjustment, denoise, or
    thresholding.
4.  Detect text regions and recognize text.
5.  Parse trait label and count from each row.
6.  Match label to the selected set catalog.
7.  Attach confidence and raw OCR text.
8.  Send a recognition result to temporal validation.

PaddleOCR is the initial candidate. Benchmark it against actual TFT
screenshots at the resolutions and UI scales intended for support. Keep
OCR behind an adapter so it can be replaced without changing the rest of
the application.

Do not assume OCR alone will always read every row. The implementation
may use row geometry, trait icons, or image matching as supporting
signals, but the canonical recognized output remains trait IDs and
counts.

### 4.4 Parsing and normalization

Use the selected set's catalog to resolve OCR text.

Normalization should: - Trim whitespace. - Normalize Unicode and
punctuation where appropriate. - Compare case-insensitively. - Apply
explicit aliases and known OCR-confusion substitutions only when safe. -
Prefer exact catalog matches. - Use fuzzy matching only with a
sufficiently high margin over the next candidate. - Preserve unknown
labels for diagnostics. - Never silently map an ambiguous label to an
unrelated trait.

Example catalog entry:

``` json
{
  "id": "KDA",
  "displayName": "K/DA",
  "aliases": ["KDA", "K/DA"],
  "breakpoints": [3, 5, 7, 10]
}
```

The example is illustrative and belongs to a Set 10 data pack, not to
shared core logic.

### 4.5 Recognition result contract

The worker should send structured messages. Example:

``` json
{
  "type": "recognition.result",
  "schemaVersion": 1,
  "captureTimestamp": "2026-01-01T12:00:00.000Z",
  "setId": "set-10",
  "status": "partial",
  "traits": [
    {
      "traitId": "KDA",
      "rawText": "K/DA",
      "count": 5,
      "confidence": 0.97
    },
    {
      "traitId": "Spellweaver",
      "rawText": "Spellweaver",
      "count": 2,
      "confidence": 0.93
    }
  ],
  "unknownRows": [],
  "diagnostics": {
    "ocrEngine": "paddleocr",
    "cropValid": true
  }
}
```

`status` should distinguish at least: - `ok`: all expected visible rows
were parsed and normalized. - `partial`: some rows were recognized but
one or more rows are uncertain or unknown. - `unavailable`: no usable
trait panel or no readable rows. - `error`: capture or recognition
failed.

Do not treat the example timestamp or counts as real game data.

### 4.6 Temporal validation

The recognizer may produce transient errors. A temporal filter should
publish a stable composition only after configurable validation.

Initial behavior: - Require the same normalized trait/count state in
2--3 consecutive usable captures before applying it. - Use a short
debounce window to avoid reacting to animation or intermediate UI
states. - Preserve the last-known-good composition during brief capture
failures. - Expose stale status and last successful capture time to the
UI. - Do not preserve stale state indefinitely without indicating that
it is stale. - Unknown or low-confidence rows should be visible in
diagnostics and should not activate rules unless the user explicitly
configures that behavior.

The exact thresholds should be configurable and tuned using recorded
screenshots.

## 5. Composition model

The composition is a list of trait IDs and displayed counts. It does not
need champion identities.

``` ts
interface TraitCount {
  traitId: string;
  count: number;
  confidence?: number;
  activeBreakpoint?: number;
  nextBreakpoint?: number;
}

interface CompositionState {
  setId: string;
  traits: TraitCount[];
  status: "stable" | "partial" | "stale" | "unavailable";
  capturedAt: string;
  revision: number;
}
```

Important distinction: - `count` is the number displayed by TFT. -
`activeBreakpoint` is derived from the selected set's breakpoint
metadata, if available. - `nextBreakpoint` is the next configured
breakpoint, if available.

The count is the primary recognized value. Breakpoint values are derived
metadata and must not replace the count.

Do not assume all traits have numeric breakpoints or that every TFT set
displays traits in the same way. Support traits without breakpoint
metadata.

## 6. Game-set data

Store versioned static data in JSON, separate from the application code.

Suggested layout:

``` text
packages/game-data/
  schemas/
    set.schema.json
    trait.schema.json
  sets/
    set-10/
      manifest.json
      traits.json
    <future-set-id>/
      manifest.json
      traits.json
```

Suggested trait schema:

``` ts
interface TraitDefinition {
  id: string;
  displayName: string;
  aliases: string[];
  breakpoints?: number[];
  iconAsset?: string;
}

interface GameSetDefinition {
  id: string;
  displayName: string;
  dataVersion: string;
  traits: TraitDefinition[];
}
```

Keep set IDs and trait IDs stable within the app's data pack. Validate
JSON files against schemas at load time. Unknown set or trait IDs should
produce visible diagnostics.

Use authoritative, appropriately licensed static game data and assets.
Verify the current source and terms before bundling data or artwork. Do
not assume an API provides every trait detail required.

## 7. Rule engine

Rules evaluate normalized trait state and produce a desired audio mix.

### 7.1 Condition types

MVP condition types: - `trait_count`: trait count comparison. -
`trait_present`: trait exists in the recognized panel. -
`trait_breakpoint`: a configured breakpoint is active. - `all`: all
child conditions must match. - `any`: at least one child condition must
match. - `not`: invert a child condition.

Future candidates: - Specific combinations of traits. - Set-specific
conditions. - Manual override conditions.

Example condition:

``` json
{
  "type": "trait_count",
  "traitId": "KDA",
  "operator": "gte",
  "value": 5
}
```

### 7.2 Rule definition

``` ts
interface MusicRule {
  id: string;
  name: string;
  enabled: boolean;
  priority: number;
  condition: RuleCondition;
  layerActions: LayerAction[];
  transition: TransitionConfig;
}

interface LayerAction {
  layerId: string;
  mode: "set" | "add";
  gain: number; // normalized 0..1
}

interface TransitionConfig {
  mode: "immediate" | "next-bar";
  fadeInMs: number;
  fadeOutMs: number;
}
```

The exact rule schema may evolve. Keep it versioned and validate
imported configuration.

### 7.3 Conflict resolution

Do not let a high-priority rule automatically disable all lower-priority
rules. Rules should contribute to a target mix.

Define deterministic conflict behavior: - Multiple rules may activate
different layers simultaneously. - If multiple rules control the same
layer, resolve using an explicit policy. - Initial recommended policy:
highest priority wins for `set` actions; additive actions are combined
and clamped to the supported gain range. - Make the resolution visible
in diagnostics. - Avoid relying on rule evaluation order.

The rule engine should be a pure TypeScript module: given a composition
and rule configuration, it returns the desired mix and an explanation of
which rules matched.

## 8. Music engine

### 8.1 Audio model

A music pack contains one or more audio layers (stems). Layers intended
to play together must be musically synchronized.

``` ts
interface MusicPack {
  id: string;
  name: string;
  bpm?: number;
  beatsPerBar?: number;
  layers: AudioLayerDefinition[];
}

interface AudioLayerDefinition {
  id: string;
  name: string;
  sourcePath: string;
  defaultGain: number;
  loopStartSeconds?: number;
  loopEndSeconds?: number;
  enabled: boolean;
}
```

Local audio files are the recommended MVP source. Support for specific
codecs depends on the chosen decoding path and should be tested. Do not
promise every format until validated.

### 8.2 Playback behavior

-   Keep a persistent playback timeline.
-   Load and decode audio before a layer is needed when practical.
-   Start synchronized stems against a shared timeline.
-   Change gain rather than restarting a source when possible.
-   Smooth all gain changes to avoid clicks.
-   Support looping with correctly configured loop boundaries.
-   Provide master gain, per-layer gain, mute, and pause controls.
-   Handle missing or unreadable files gracefully.

Use Web Audio API nodes such as `AudioContext`, `AudioBufferSourceNode`,
and `GainNode`. Encapsulate audio operations behind a music-engine API
so the UI and rule engine do not manipulate raw nodes.

### 8.3 Transition modes

-   `immediate`: schedule a smooth gain ramp as soon as a stable
    composition is accepted.
-   `next-bar`: schedule the gain change at the next calculated bar
    boundary.

For beat-aligned transitions, layers in a pack need compatible BPM,
meter, start offsets, sample rates, and loop lengths. If timing metadata
is missing or invalid, fall back to a smooth immediate transition and
report why.

Avoid restarting the entire soundtrack when a trait changes.

### 8.4 Desired mix contract

``` ts
interface DesiredLayerGain {
  layerId: string;
  gain: number; // 0..1
  matchedRuleIds: string[];
}

interface DesiredMix {
  packId: string;
  layers: DesiredLayerGain[];
  generatedAt: string;
}
```

## 9. Main UI screens

### Now Playing

-   Capture/recognition status.
-   Selected set.
-   Current detected trait list and counts.
-   Confidence or partial-recognition warnings.
-   Active music pack.
-   Active layers and their current gains.
-   Master volume, pause, and mute.
-   Last successful recognition timestamp.

### Calibration

-   Capture source selector.
-   Screenshot preview.
-   Adjustable crop rectangle.
-   Crop preview.
-   Save and recalibrate controls.

### Music Studio

-   Create and edit music packs.
-   Import local audio files.
-   Configure layer names, gain, BPM, meter, offsets, and loop points.
-   Preview layers and combined mix.
-   Validate synchronization metadata.

### Rule Editor

-   Select trait and comparison operator.
-   Set count or breakpoint threshold.
-   Select target music layers and gains.
-   Set priority and transition mode.
-   Preview rule matches against a simulated composition.

### Composition Simulator

-   Select a set.
-   Manually add/remove traits and adjust counts.
-   See matched rules and resulting target mix.
-   Test transitions without launching TFT.

## 10. IPC and worker communication

Use a versioned message protocol. Prefer a local WebSocket or Electron
IPC boundary with explicit schemas.

Messages from desktop to recognition worker: - `capture.start` -
`capture.stop` - `calibration.update` - `set.select` -
`recognition.configure`

Messages from worker to desktop: - `worker.ready` -
`recognition.result` - `recognition.status` - `recognition.error`

Requirements: - Validate every incoming message. - Include
`schemaVersion`. - Include timestamps and request IDs where useful. -
Handle worker disconnect and restart. - Do not expose the local worker
port to the network. - Bind local WebSocket to loopback only, or prefer
Electron IPC if it meets the capture/worker design. - Never execute
commands or paths received from untrusted messages.

## 11. Suggested repository structure

``` text
tft-soundtrack/
  apps/
    desktop/
      electron/
      src/
        components/
        pages/
        stores/
        composables/
    recognition/
      capture/
      panel/
      ocr/
      processing/
      communication/
  packages/
    shared-types/
    game-data/
    composition-engine/
    rule-engine/
    music-engine/
  data/
    sets/
  music/
    packs/
  docs/
    README.md
    ARCHITECTURE.md
    IMPLEMENTATION_PLAN.md
    AI_CODING_GUIDE.md
```

Use a pnpm workspace for TypeScript packages. The Python worker may have
its own `pyproject.toml` and dependency lockfile.

## 12. Error handling and observability

Expose understandable statuses rather than silently failing: - Capture
source unavailable. - Calibration missing or invalid. - Trait panel not
found/readable. - OCR returned partial results. - Unknown trait label. -
Low-confidence count. - Selected set does not match recognized traits. -
Worker disconnected. - Audio file missing or unsupported. - Audio timing
metadata invalid.

Keep diagnostic logs local. Avoid recording or retaining full gameplay
screenshots by default. If a debug screenshot feature is added, make it
explicit and user-controlled.

## 13. Non-goals

Not part of the initial product: - Champion portrait recognition. -
Board or bench detection. - Inferring traits from champion identities. -
Gameplay recommendations or tactical advice. - Opponent scouting or
composition tracking. - Game-memory reading, injection, or
modification. - Cloud accounts or online synchronization. -
Streaming-service playback integrations.

## 14. Policy and distribution

The product is intended to read visible trait labels/counts solely to
control music. It must not expand into gameplay advice or competitive
analysis without a separate policy review. Review Riot's current
developer terms, third-party product rules, and any relevant
restrictions before public distribution. Use only music and game assets
the user is licensed to use; do not bundle copyrighted soundtrack files
without permission.
