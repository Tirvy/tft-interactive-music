# TFT Soundtrack Companion

A desktop companion for Teamfight Tactics that reads the active trait
panel from the game UI and uses the detected trait names and counts to
drive a layered, adaptive soundtrack.

The product is inspired by the dynamic music experience of TFT Set 10 /
Remix Rumble, but should support configurable music packs and multiple
TFT sets.

## Product goals

-   Automatically read trait names and displayed counts from the TFT
    trait panel.
-   Convert OCR output into a normalized trait composition.
-   Activate, fade, and mix synchronized audio layers based on
    user-defined rules.
-   Let users import local audio, build music packs, and configure rules
    without editing code.
-   Keep recognition, composition logic, rules, and playback independent
    so each can be tested separately.
-   Operate locally after game data and audio assets have been
    configured.

## Core interaction

1.  Capture the TFT game window.
2.  Read a calibrated region containing the trait panel.
3.  Recognize trait labels and their displayed counts.
4.  Normalize recognized labels against the selected set's trait
    catalog.
5.  Validate readings over time and publish a stable composition.
6.  Evaluate music rules.
7.  Smoothly update the active audio layers, optionally quantizing
    changes to the next musical bar.

## Important product boundary

The app is a soundtrack companion, not a gameplay assistant. It should
not provide tactical recommendations, scouting, opponent analysis, or
competitive gameplay information. It reads only the visible trait panel
for the purpose of selecting music. Before public distribution, review
Riot's current third-party product and game policies and seek
clarification if needed.

## Documentation

-   [Architecture](ARCHITECTURE.md): components, data flow, interfaces,
    and technical decisions.
-   [Implementation plan](IMPLEMENTATION_PLAN.md): milestones,
    acceptance criteria, and testing.
-   [AI coding guide](AI_CODING_GUIDE.md): instructions and constraints
    for coding assistants.

## Proposed stack

  Area                            Initial choice
  ------------------------------- --------------------------------------------
  Desktop shell                   Electron
  UI                              Vue 3 + TypeScript
  UI state                        Pinia
  Recognition worker              Python
  Image processing                OpenCV
  OCR                             PaddleOCR, subject to prototype evaluation
  Worker communication            Local WebSocket
  Composition and rules           TypeScript packages
  Audio                           Web Audio API
  Persistent user configuration   SQLite
  Static set catalog              Versioned JSON

These are proposed defaults, not immutable requirements. Validate the
OCR library and audio architecture with small prototypes before
committing to complex implementation.

## MVP scope

The first useful version should: - Capture a selected TFT window or
user-selected screen source. - Let the user calibrate the trait-panel
crop. - Recognize trait names and counts. - Display raw OCR output,
normalized traits, confidence, and recognition status. - Allow a
manually supplied composition for testing. - Play a base layer plus
rule-controlled synchronized layers. - Support local audio files and
smooth gain transitions. - Provide a simple rule configuration UI.

Do not make champion recognition, board-unit detection,
champion-to-trait inference, streaming-service integration, or cloud
services part of the MVP.
