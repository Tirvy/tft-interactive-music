import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { afterAll, describe, expect, it } from 'vitest'
import { resolveSetCatalogPath } from './catalog'

const directories: string[] = []

function makeRecognitionDir(): string {
  const directory = mkdtempSync(join(tmpdir(), 'tft-catalog-'))
  directories.push(directory)
  return directory
}

function writeFile(directory: string, relativePath: string): void {
  const target = join(directory, relativePath)
  mkdirSync(dirname(target), { recursive: true })
  writeFileSync(target, '{}')
}

afterAll(() => {
  for (const directory of directories.splice(0)) {
    rmSync(directory, { recursive: true, force: true })
  }
})

describe('resolveSetCatalogPath', () => {
  it('prefers the checked-in set data', () => {
    const directory = makeRecognitionDir()
    writeFile(directory, join('data', 'sets', 'set-18-ru.json'))
    writeFile(directory, join('tests', 'fixtures', 'catalog', 'set-18-ru.fixture.json'))

    const resolved = resolveSetCatalogPath(directory)

    expect(resolved).toEqual({
      path: join(directory, 'data', 'sets', 'set-18-ru.json'),
      origin: 'data',
    })
  })

  it('falls back to the test fixture when set data is missing', () => {
    const directory = makeRecognitionDir()
    writeFile(directory, join('tests', 'fixtures', 'catalog', 'set-18-ru.fixture.json'))

    const resolved = resolveSetCatalogPath(directory, 'set-18')

    expect(resolved).toEqual({
      path: join(directory, 'tests', 'fixtures', 'catalog', 'set-18-ru.fixture.json'),
      origin: 'fixture',
    })
  })

  it('returns null for an unknown set', () => {
    expect(resolveSetCatalogPath(makeRecognitionDir(), 'set-99')).toBeNull()
  })

  it('rejects unsafe set ids instead of joining them into a path', () => {
    const directory = makeRecognitionDir()
    writeFile(directory, join('data', 'sets', 'set-18-ru.json'))

    expect(resolveSetCatalogPath(directory, '..\\..\\evil')).toBeNull()
    expect(resolveSetCatalogPath(directory, '../evil')).toBeNull()
  })

  it('returns null without a recognition directory', () => {
    expect(resolveSetCatalogPath(null)).toBeNull()
  })
})
