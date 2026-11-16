# TFT Soundtrack Companion

An attempt to recreate Teamfight Tactics set music through adaptive,
layer-based playback driven by trait-panel recognition.

This repository currently contains the desktop foundation for Milestones
0 and 1 plus the first half of Milestone 2: a pnpm workspace, shared
TypeScript contracts, an Electron + Vue shell with settings and
capture-source selection, a Python recognition worker that analyzes
saved captures, and verified capture and recognition smoke tests.

Recognition is wired from the capture screen through IPC to the Python
worker. Audio and the rule engine are not implemented yet.

## Workspace layout

```text
.
├─ apps/
│  ├─ desktop/           Electron main, preload, and Vue 3 renderer
│  └─ recognition/       Python recognition package and worker
├─ packages/
│  └─ shared-types/      Zod schemas and TypeScript contracts
├─ docs/                 Architecture, decisions, and plan documents
└─ tests/                Recognition fixtures and screenshots
```

- `apps/desktop` owns window creation, settings persistence, capture
  enumeration and file writes, IPC, and worker process management. Vue
  components render state; they do not contain recognition or audio
  business logic.
- `apps/recognition` owns all image recognition and the stdio worker.
- `packages/shared-types` is the single source of truth for IPC, worker
  protocol, capture, settings, and recognition result shapes.

## Prerequisites

- Node.js 22 or newer
- pnpm 9.15.9 (`corepack enable`)
- Python 3.12 for the recognition worker with PaddleOCR dependencies
- Windows 11 is the first target OS

## Setup

```powershell
pnpm install
```

The desktop app resolves the worker's Python in this order: the path saved
in settings, `apps/recognition/.venv312`, `apps/recognition/.venv`, then
`python` on `PATH`. To create the preferred environment:

```powershell
cd apps\recognition
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -e ".[dev,ocr]"
```

The first recognition run downloads the PaddleOCR models into the PaddleX
cache. Without the OCR extra the worker still starts and reports stub
capabilities, but analysis requests fail.

## Commands

Run from the repository root:

| Command | Purpose |
| --- | --- |
| `pnpm dev` | Start the Electron app in development mode with Vite HMR. |
| `pnpm build` | Build the desktop main, preload, and renderer bundles. |
| `pnpm typecheck` | Typecheck every TypeScript workspace package. |
| `pnpm test` | Run Vitest suites, including the real Python worker lifecycle test. |
| `pnpm test:recognition` | Run the Python recognition tests with `python -m pytest`. |
| `pnpm lint` | Run ESLint over the workspace. |
| `pnpm format` | Format with Prettier. |
| `pnpm format:check` | Verify formatting without writing. |

Desktop-only diagnostics:

```powershell
pnpm --filter @tft/desktop smoke             # launch, mount renderer, start/stop worker
pnpm --filter @tft/desktop smoke:capture     # capture the primary screen and save a PNG
pnpm --filter @tft/desktop smoke:recognition # analyze a known screenshot end to end
```

All smoke modes exit with a non-zero code on failure and print a JSON
summary. Capture output is written under
`%APPDATA%\TFT Soundtrack Companion\captures`; the recognition smoke
deletes its temporary capture afterwards. The first recognition smoke can
take one to two minutes while PaddleOCR loads its models and runs.

## Application data

Settings, logs, and captures live in the Electron `userData` directory:

```text
%APPDATA%\TFT Soundtrack Companion\
  settings.json
  logs\main.log
  captures\
```

Settings are validated JSON written atomically by the main process.
Missing fields are filled from defaults, and a corrupt file is backed up
and replaced with defaults. Validation failures on save are surfaced in
the UI.

## Documents

- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md):
  milestones and acceptance criteria.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): package boundaries and
  data flow.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): settled choices and open
  questions.
- [`docs/CAPTURE_SPIKE.md`](docs/CAPTURE_SPIKE.md): capture method,
  verification results, and the manual test checklist.
- [`apps/recognition/README.md`](apps/recognition/README.md): recognition
  POC and worker protocol.
