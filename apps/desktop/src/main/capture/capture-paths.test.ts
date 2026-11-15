import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  captureFileName,
  isPathInside,
  resolveCaptureDirectory,
  sanitizeFileNamePart,
} from './capture-paths'

describe('capture paths', () => {
  it('sanitizes source names for Windows filenames', () => {
    expect(sanitizeFileNamePart('League of Legends: TFT')).toBe('League-of-Legends-TFT')
    expect(sanitizeFileNamePart('   ')).toBe('source')
  })

  it('builds a timestamped PNG filename', () => {
    const fileName = captureFileName(
      'League of Legends: TFT',
      '2026-11-15T10:20:30.456Z',
      '12345678-aaaa-bbbb-cccc-dddddddddddd',
    )

    expect(fileName).toBe('tft-capture-2026-11-15T10-20-30-456Z-League-of-Legends-TFT-12345678.png')
  })

  it('uses the configured directory when present', () => {
    const configured = resolve('captures', 'custom')
    expect(resolveCaptureDirectory(configured, resolve('user-data'))).toBe(configured)
  })

  it('defaults to the userData captures directory', () => {
    const userData = resolve('user-data')
    expect(resolveCaptureDirectory(null, userData)).toBe(resolve(userData, 'captures'))
  })

  it('detects paths inside and outside a directory', () => {
    const parent = resolve('captures')
    expect(isPathInside(parent, resolve(parent, 'frame.png'))).toBe(true)
    expect(isPathInside(parent, resolve('other', 'frame.png'))).toBe(false)
    expect(isPathInside(parent, parent)).toBe(false)
  })
})
