import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, describe, expect, it } from 'vitest'
import { findRecognitionDir } from './paths'

const temporaryDirectories: string[] = []

afterAll(() => {
  for (const directory of temporaryDirectories) {
    rmSync(directory, { recursive: true, force: true })
  }
})

describe('findRecognitionDir', () => {
  it('finds the recognition package from a nested app directory', () => {
    const root = mkdtempSync(join(tmpdir(), 'tft-paths-'))
    temporaryDirectories.push(root)

    const recognition = join(root, 'apps', 'recognition')
    const desktop = join(root, 'apps', 'desktop')
    mkdirSync(join(recognition, 'src', 'tft_recognition'), { recursive: true })
    mkdirSync(desktop, { recursive: true })
    writeFileSync(join(recognition, 'pyproject.toml'), '[project]\nname="x"\n', 'utf8')

    expect(findRecognitionDir([desktop])).toBe(recognition)
  })

  it('returns null when no recognition package exists', () => {
    const root = mkdtempSync(join(tmpdir(), 'tft-paths-empty-'))
    temporaryDirectories.push(root)

    expect(findRecognitionDir([root])).toBeNull()
  })
})
