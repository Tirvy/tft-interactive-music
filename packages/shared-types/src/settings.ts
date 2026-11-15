import { z } from 'zod'

export const appViewSchema = z.enum(['now-playing', 'capture', 'worker', 'settings'])

export const captureSettingsSchema = z.object({
  preferredSourceId: z.string().min(1).nullable(),
  preferredSourceName: z.string().nullable(),
  /** Absolute directory for saved captures. `null` means `<userData>/captures`. */
  saveDirectory: z.string().min(1).nullable(),
  frameRate: z.number().int().min(1).max(30),
})

export const workerSettingsSchema = z.object({
  /** Explicit Python executable. `null` lets the app probe known venv locations. */
  pythonPath: z.string().min(1).nullable(),
  autoStart: z.boolean(),
  startupTimeoutMs: z.number().int().min(3000).max(120_000),
  heartbeatIntervalMs: z.number().int().min(500).max(30_000),
  heartbeatTimeoutMs: z.number().int().min(1000).max(120_000),
})

export const uiSettingsSchema = z.object({
  lastView: appViewSchema,
})

export const appSettingsSchema = z
  .object({
    capture: captureSettingsSchema,
    worker: workerSettingsSchema,
    ui: uiSettingsSchema,
  })
  .superRefine((settings, context) => {
    if (settings.worker.heartbeatTimeoutMs <= settings.worker.heartbeatIntervalMs) {
      context.addIssue({
        code: 'custom',
        path: ['worker', 'heartbeatTimeoutMs'],
        message: 'heartbeatTimeoutMs must be greater than heartbeatIntervalMs',
      })
    }
  })

export const captureSettingsPatchSchema = captureSettingsSchema.partial()
export const workerSettingsPatchSchema = workerSettingsSchema.partial()
export const uiSettingsPatchSchema = uiSettingsSchema.partial()

export const appSettingsPatchSchema = z.object({
  capture: captureSettingsPatchSchema.optional(),
  worker: workerSettingsPatchSchema.optional(),
  ui: uiSettingsPatchSchema.optional(),
})

export type AppView = z.infer<typeof appViewSchema>
export type CaptureSettings = z.infer<typeof captureSettingsSchema>
export type WorkerSettings = z.infer<typeof workerSettingsSchema>
export type UiSettings = z.infer<typeof uiSettingsSchema>
export type AppSettings = z.infer<typeof appSettingsSchema>
export type AppSettingsPatch = z.infer<typeof appSettingsPatchSchema>

export const DEFAULT_APP_SETTINGS: AppSettings = {
  capture: {
    preferredSourceId: null,
    preferredSourceName: null,
    saveDirectory: null,
    frameRate: 4,
  },
  worker: {
    pythonPath: null,
    autoStart: true,
    startupTimeoutMs: 20_000,
    heartbeatIntervalMs: 5000,
    heartbeatTimeoutMs: 14_000,
  },
  ui: {
    lastView: 'now-playing',
  },
}

/**
 * Merge a partial patch over a full settings object and validate the result.
 * Unknown keys are stripped so stale settings files remain loadable.
 */
export function mergeSettings(base: AppSettings, patch: unknown): AppSettings {
  const parsedPatch = appSettingsPatchSchema.parse(patch ?? {})

  return appSettingsSchema.parse({
    ...base,
    capture: { ...base.capture, ...(parsedPatch.capture ?? {}) },
    worker: { ...base.worker, ...(parsedPatch.worker ?? {}) },
    ui: { ...base.ui, ...(parsedPatch.ui ?? {}) },
  })
}

export function withSettingsDefaults(input: unknown): AppSettings {
  return mergeSettings(DEFAULT_APP_SETTINGS, input)
}
