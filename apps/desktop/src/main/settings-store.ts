import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from 'node:fs'
import { dirname } from 'node:path'
import type { AppSettings, AppSettingsPatch } from '@tft/shared-types/settings'
import {
  DEFAULT_APP_SETTINGS,
  mergeSettings,
  withSettingsDefaults,
} from '@tft/shared-types/settings'
import { errorMessage } from './errors'
import type { Logger } from './logger'

/**
 * Typed JSON settings store with atomic writes and corruption recovery.
 * Settings live in Electron's userData directory.
 */
export class SettingsStore {
  private settings: AppSettings = DEFAULT_APP_SETTINGS

  constructor(
    private readonly filePath: string,
    private readonly logger: Logger,
  ) {}

  load(): AppSettings {
    if (!existsSync(this.filePath)) {
      this.settings = DEFAULT_APP_SETTINGS
      this.write(this.settings)
      return this.settings
    }

    try {
      const raw: unknown = JSON.parse(readFileSync(this.filePath, 'utf8'))
      this.settings = withSettingsDefaults(raw)
      return this.settings
    } catch (error) {
      const backupPath = `${this.filePath}.invalid-${Date.now()}`

      try {
        copyFileSync(this.filePath, backupPath)
      } catch (backupError) {
        this.logger.warn('settings.backup-failed', {
          backupPath,
          message: errorMessage(backupError),
        })
      }

      this.logger.error('settings.invalid', {
        message: errorMessage(error),
        backupPath,
      })
      this.settings = DEFAULT_APP_SETTINGS
      this.write(this.settings)
      return this.settings
    }
  }

  get(): AppSettings {
    return this.settings
  }

  update(patch: AppSettingsPatch): AppSettings {
    const next = mergeSettings(this.settings, patch)
    this.write(next)
    this.settings = next
    return next
  }

  private write(settings: AppSettings): void {
    mkdirSync(dirname(this.filePath), { recursive: true })
    const temporaryPath = `${this.filePath}.tmp`
    writeFileSync(temporaryPath, `${JSON.stringify(settings, null, 2)}\n`, 'utf8')
    renameSync(temporaryPath, this.filePath)
  }
}
