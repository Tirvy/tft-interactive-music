import { describe, expect, it } from 'vitest'
import {
  DEFAULT_APP_SETTINGS,
  mergeSettings,
  workerSettingsSchema,
  withSettingsDefaults,
} from './settings'

describe('app settings', () => {
  it('returns defaults for an empty file', () => {
    expect(withSettingsDefaults({})).toEqual(DEFAULT_APP_SETTINGS)
  })

  it('merges nested patches without dropping sibling values', () => {
    const merged = mergeSettings(DEFAULT_APP_SETTINGS, {
      capture: { preferredSourceId: 'screen:1:0', frameRate: 8 },
    })

    expect(merged.capture.preferredSourceId).toBe('screen:1:0')
    expect(merged.capture.frameRate).toBe(8)
    expect(merged.capture.preferredSourceName).toBeNull()
    expect(merged.worker).toEqual(DEFAULT_APP_SETTINGS.worker)
  })

  it('strips unknown keys from old settings files', () => {
    const settings = withSettingsDefaults({
      capture: { frameRate: 2 },
      legacySetting: true,
    })

    expect(settings.capture.frameRate).toBe(2)
    expect('legacySetting' in settings).toBe(false)
  })

  it('rejects a frame rate outside the supported range', () => {
    expect(() => withSettingsDefaults({ capture: { frameRate: 0 } })).toThrow()
  })

  it('rejects a heartbeat timeout that is shorter than the interval', () => {
    expect(() =>
      workerSettingsSchema.parse({
        pythonPath: null,
        autoStart: true,
        startupTimeoutMs: 20_000,
        heartbeatIntervalMs: 5000,
        heartbeatTimeoutMs: 4000,
      }),
    ).not.toThrow()

    expect(() =>
      withSettingsDefaults({
        worker: { heartbeatIntervalMs: 5000, heartbeatTimeoutMs: 4000 },
      }),
    ).toThrow(/heartbeatTimeoutMs/)
  })
})
