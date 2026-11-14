# Implementation Plan

## Guiding strategy

Build and verify the music engine and recognition pipeline
independently, then integrate them. The first prototype should not
depend on a live TFT match for every test.

## Milestone 0: Repository and technical spikes

### Tasks

-   Create pnpm workspace for the Electron/Vue app and TypeScript
    packages.
-   Create Python recognition worker project with a lockfile.
-   Add shared TypeScript types and JSON schemas.
-   Prototype Electron capture at the intended display resolutions.
-   Prototype OCR on representative TFT trait-panel screenshots.
-   Prototype synchronized multi-layer playback with Web Audio API.
-   Record benchmark results and choose final OCR approach.

### Acceptance criteria

-   App launches on the target desktop OS.
-   A screenshot can be captured and saved for a local test.
-   OCR prototype can return text regions and confidence values from
    sample crops.
-   Two or more audio stems can play in sync and change gain without
    restarting.
-   Technical decisions and known limitations are documented.

Do not proceed on the assumption that OCR will work until it has been
tested against real screenshots at different resolutions and UI scales.

## Milestone 1: Desktop foundation

### Tasks

-   Create Electron main and Vue renderer.
-   Add Pinia and routing or a simple screen-navigation structure.
-   Add application settings persistence.
-   Add capture-source selection.
-   Add worker lifecycle management and health status.
-   Add basic logging and error presentation.

### Acceptance criteria

-   App starts and closes cleanly.
-   User can select a capture source.
-   Worker can be started, stopped, and restarted.
-   Worker disconnect is visible in the UI.
-   No recognition or audio business logic is embedded in Vue
    components.

## Milestone 2: Trait-panel calibration and OCR

### Tasks

-   Implement screenshot preview.
-   Implement crop-rectangle selection.
-   Persist normalized crop coordinates.
-   Implement crop preprocessing.
-   Implement OCR adapter.
-   Parse trait names and numeric counts.
-   Load selected set catalog.
-   Normalize OCR labels to trait IDs.
-   Display unknown rows and confidence.
-   Add a screenshot fixture set for regression tests.

### Acceptance criteria

-   User can calibrate and save the trait-panel region.
-   Crop remains correct when the capture resolution changes
    proportionally.
-   Recognized rows are shown with raw text, normalized trait name,
    count, and confidence.
-   Unknown labels are not silently mapped.
-   Invalid calibration produces a clear error.
-   OCR adapter can be replaced without changing the composition model.

## Milestone 3: Stable composition state

### Tasks

-   Implement recognition result schema and validation.
-   Implement temporal filtering/debouncing.
-   Implement last-known-good state with stale status.
-   Implement composition revision numbers.
-   Add manual composition simulator.
-   Add selected-set switching.

### Acceptance criteria

-   A single transient OCR error does not immediately change the active
    composition.
-   A stable new reading updates the composition after the configured
    validation window.
-   Capture failures preserve the previous state but mark it
    stale/unavailable as appropriate.
-   Simulator can create the same composition shape as live recognition.
-   Composition package has unit tests and does not depend on Electron
    or Python.

## Milestone 4: Rule engine

### Tasks

-   Define versioned rule schema.
-   Implement trait presence and count conditions.
-   Implement `all`, `any`, and `not` condition groups.
-   Implement deterministic priority/conflict resolution.
-   Produce desired mix plus matched-rule explanations.
-   Add rule fixtures and unit tests.

### Acceptance criteria

-   Same input composition and rules always produce the same desired
    mix.
-   Multiple rules can activate different layers simultaneously.
-   Conflicts controlling the same layer are resolved deterministically.
-   Invalid rules are rejected with actionable validation errors.
-   Rule evaluation is independent of the UI and audio engine.

## Milestone 5: Layered music engine

### Tasks

-   Implement local audio import and file validation.
-   Implement music pack and layer metadata.
-   Implement persistent audio timeline.
-   Implement synchronized stem playback.
-   Implement per-layer and master gain.
-   Implement smooth fade-in/fade-out.
-   Implement immediate and next-bar transitions.
-   Implement fallback when timing metadata is unavailable.
-   Add audio engine diagnostics.

### Acceptance criteria

-   At least two synchronized stems can play together.
-   Changing a trait-controlled layer does not restart unaffected
    layers.
-   Gain changes are click-free under normal operating conditions.
-   Loop points work as configured.
-   Next-bar transitions occur at the expected boundary when timing
    metadata is valid.
-   Missing files and invalid metadata are reported clearly.

## Milestone 6: End-to-end integration

### Tasks

-   Connect stable composition updates to rule evaluation.
-   Connect desired mix to audio engine.
-   Display detected traits, matched rules, and active layers.
-   Add pause, mute, master gain, and manual override.
-   Add manual composition-to-music preview.
-   Test with live TFT captures.

### Acceptance criteria

-   A recognized trait-count change can activate or deactivate
    configured layers.
-   Unchanged compositions do not cause unnecessary audio updates.
-   Partial or stale recognition does not cause erratic switching.
-   Manual simulator and live recognition use the same composition and
    rule pipeline.
-   User can understand why each layer is active.

## Milestone 7: Music Studio and polish

### Tasks

-   Build music pack editor.
-   Build rule editor.
-   Add BPM, meter, offset, and loop-point controls.
-   Add pack import/export with schema versioning.
-   Add set data validation and update workflow.
-   Add accessibility and keyboard shortcuts.
-   Package and test installers for target OS.

### Acceptance criteria

-   User can create a pack without editing JSON manually.
-   User can create and test a rule without editing JSON manually.
-   Exported packs can be imported with validation.
-   Invalid or missing assets produce useful messages.
-   App can run offline after setup.

## Test strategy

### Recognition tests

-   Exact trait label.
-   OCR punctuation variation.
-   Known alias.
-   Common OCR confusion.
-   Unknown trait.
-   Missing count.
-   Two-digit count, if displayed by the game.
-   Multiple rows.
-   Different resolutions and UI scales.
-   Partial panel crop.
-   Empty or obscured panel.
-   Capture interruption.

Store representative screenshots as test fixtures only when their use
and retention are appropriate. Keep fixture images out of public
repositories unless redistribution is permitted.

### Composition tests

-   Empty composition.
-   One trait.
-   Multiple traits.
-   Count changes.
-   Trait disappears.
-   Unknown trait.
-   Set switch.
-   Breakpoint calculation.
-   Trait with no breakpoint metadata.

### Rule-engine tests

-   Single matching rule.
-   Non-matching rule.
-   Count equals/greater-than/less-than.
-   Multiple simultaneous rules.
-   Priority conflict on one layer.
-   Additive actions and gain clamping.
-   Disabled rule.
-   Nested `all`, `any`, and `not`.

### Audio tests

-   Load and decode supported formats.
-   Two or more synchronized stems.
-   Gain ramp.
-   Fade to zero.
-   Loop boundaries.
-   Next-bar transition.
-   Invalid BPM or loop metadata.
-   Missing audio file.
-   Pause/resume.
-   Device output change.

### End-to-end tests

-   Stable OCR composition activates a layer.
-   Count breakpoint activates another layer.
-   Temporary OCR failure does not cause a false transition.
-   A real trait change updates the mix without restarting unrelated
    stems.
-   Manual simulator reproduces the same behavior.

## Definition of done for MVP

The MVP is complete when a user can: 1. Launch the desktop app. 2.
Select the TFT capture source. 3. Calibrate the visible trait panel. 4.
See trait names and displayed counts recognized. 5. Correctly identify
partial/unknown/stale recognition states. 6. Load a local music pack
with synchronized stems. 7. Create a trait-count rule that controls a
layer. 8. Test the rule with the composition simulator. 9. Run the app
during TFT and hear the soundtrack adapt without abrupt restarts.
