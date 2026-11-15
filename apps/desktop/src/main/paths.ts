import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

/**
 * Locate the Python recognition project from either the repo root or the
 * desktop package directory. Packaged builds will need an explicit worker
 * location later; until then this keeps dev and test runs predictable.
 */
export function findRecognitionDir(
  startDirectories: string[],
  exists: (path: string) => boolean = existsSync,
): string | null {
  const seen = new Set<string>()

  for (const startDirectory of startDirectories) {
    let directory = resolve(startDirectory)

    for (let depth = 0; depth < 10; depth += 1) {
      const candidates = [join(directory, 'apps', 'recognition'), join(directory, 'recognition')]

      for (const candidate of candidates) {
        if (seen.has(candidate)) {
          continue
        }
        seen.add(candidate)

        if (
          exists(join(candidate, 'pyproject.toml')) &&
          exists(join(candidate, 'src', 'tft_recognition'))
        ) {
          return candidate
        }
      }

      const parent = dirname(directory)
      if (parent === directory) {
        break
      }
      directory = parent
    }
  }

  return null
}
