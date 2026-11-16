import { existsSync } from 'node:fs'
import { join } from 'node:path'

/** MVP ships a Russian catalog for Set 18 only. */
export const DEFAULT_SET_ID = 'set-18'
export const DEFAULT_LOCALE = 'ru'

export interface CatalogResolution {
  path: string
  /** Where the catalog came from, for logging. */
  origin: 'data' | 'fixture'
}

const setIdPattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

/**
 * Resolve the catalog file for a set.
 *
 * Prefers the checked-in set data under `data/sets`, then falls back to the
 * recognition test fixture so the app is usable before the catalog is filled
 * in. The renderer never supplies a catalog path; it only names a set id.
 */
export function resolveSetCatalogPath(
  recognitionDir: string | null,
  setId: string = DEFAULT_SET_ID,
): CatalogResolution | null {
  if (!recognitionDir || !setIdPattern.test(setId)) {
    return null
  }

  const fileName = `${setId}-${DEFAULT_LOCALE}`
  const dataPath = join(recognitionDir, 'data', 'sets', `${fileName}.json`)
  if (existsSync(dataPath)) {
    return { path: dataPath, origin: 'data' }
  }

  const fixturePath = join(
    recognitionDir,
    'tests',
    'fixtures',
    'catalog',
    `${fileName}.fixture.json`,
  )
  if (existsSync(fixturePath)) {
    return { path: fixturePath, origin: 'fixture' }
  }

  return null
}
