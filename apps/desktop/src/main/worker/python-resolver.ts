import { existsSync } from 'node:fs'
import { join } from 'node:path'

export type PythonOrigin = 'settings' | 'venv312' | 'venv' | 'path'

export interface ResolvedPython {
  command: string
  origin: PythonOrigin
}

interface ResolveOptions {
  platform?: NodeJS.Platform
  exists?: (path: string) => boolean
}

/**
 * Pick the Python executable used to launch the recognition worker.
 * An explicit settings value always wins. Otherwise prefer the known local
 * virtual environments, then fall back to `python`/`python3` on PATH.
 */
export function resolvePythonExecutable(
  recognitionDir: string,
  explicitPath: string | null,
  options: ResolveOptions = {},
): ResolvedPython {
  if (explicitPath) {
    return { command: explicitPath, origin: 'settings' }
  }

  const platform = options.platform ?? process.platform
  const pathExists = options.exists ?? existsSync

  const candidates: Array<{ parts: string[]; origin: PythonOrigin }> =
    platform === 'win32'
      ? [
          { parts: ['.venv312', 'Scripts', 'python.exe'], origin: 'venv312' },
          { parts: ['.venv', 'Scripts', 'python.exe'], origin: 'venv' },
        ]
      : [
          { parts: ['.venv312', 'bin', 'python3'], origin: 'venv312' },
          { parts: ['.venv312', 'bin', 'python'], origin: 'venv312' },
          { parts: ['.venv', 'bin', 'python3'], origin: 'venv' },
          { parts: ['.venv', 'bin', 'python'], origin: 'venv' },
        ]

  for (const candidate of candidates) {
    const command = join(recognitionDir, ...candidate.parts)
    if (pathExists(command)) {
      return { command, origin: candidate.origin }
    }
  }

  return { command: platform === 'win32' ? 'python' : 'python3', origin: 'path' }
}
