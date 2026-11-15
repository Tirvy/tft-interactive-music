import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { DEFAULT_APP_SETTINGS } from '@tft/shared-types/settings'
import { Logger } from './logger'
import { SettingsStore } from './settings-store'

const temporaryDirectories: string[] = []

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true })
  }
})

function createStore(): { store: SettingsStore; filePath: string; logger: Logger } {
  const directory = mkdtempSync(join(tmpdir(), 'tft-settings-'))
  temporaryDirectories.push(directory)
  const logger = new Logger(join(directory, 'logs'))
  const filePath = join(directory, 'settings.json')
  return { store: new SettingsStore(filePath, logger), filePath, logger }
}

describe('SettingsStore', () => {
  it('creates a defaults file on first load', () => {
    const { store, filePath } = createStore()

    expect(store.load()).toEqual(DEFAULT_APP_SETTINGS)
    expect(JSON.parse(readFileSync(filePath, 'utf8'))).toEqual(DEFAULT_APP_SETTINGS)
  })

  it('persists a nested update', () => {
    const { store, filePath } = createStore()
    store.load()

    const next = store.update({
      capture: { preferredSourceId: 'screen:1:0', preferredSourceName: 'Display 1' },
      worker: { autoStart: false },
    })

    expect(next.capture.preferredSourceId).toBe('screen:1:0')
    expect(next.worker.autoStart).toBe(false)
    expect(JSON.parse(readFileSync(filePath, 'utf8'))).toEqual(next)
  })

  it('quarantines invalid JSON and falls back to defaults', () => {
    const { store, filePath } = createStore()
    writeFileSync(filePath, '{ not json', 'utf8')

    expect(store.load()).toEqual(DEFAULT_APP_SETTINGS)
    expect(JSON.parse(readFileSync(filePath, 'utf8'))).toEqual(DEFAULT_APP_SETTINGS)
    expect(store.get()).toEqual(DEFAULT_APP_SETTINGS)
  })
})
