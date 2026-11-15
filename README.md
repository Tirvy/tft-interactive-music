# TFT Soundtrack Companion

An attempt to recreate Teamfight Tactics set music through adaptive,
layer-based playback driven by trait-panel recognition.

This repository currently contains the desktop foundation for Milestones
0 and 1: a pnpm workspace, shared TypeScript contracts, an Electron + Vue
shell with settings and capture-source selection, a Python recognition
worker lifecycle stub, and a verified capture spike. The recognition POC
under `apps/recognition` predates this slice. Recognition and audio
business logic are not wired into the UI yet.

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
- Python 3.12 for the recognition worker with OCR dependencies, or
  Python 3.10+ for the standard-library worker stub alone
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
.\.venv312\Scripts\python.exe -m pip install -e ".[dev]"
```

The worker lifecycle stub uses only the Python standard library, so OCR
dependencies are not required for Milestone 1 verification.

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
pnpm --filter @tft/desktop smoke           # launch, mount renderer, start/stop worker
pnpm --filter @tft/desktop smoke:capture   # capture the primary screen and save a PNG
```

Both smoke modes exit with a non-zero code on failure and print a JSON
summary. Capture output is written under
`%APPDATA%\TFT Soundtrack Companion\captures`.

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
