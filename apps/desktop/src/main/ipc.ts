import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { app, ipcMain, shell } from 'electron'
import { z } from 'zod'
import { IPC_CHANNELS, type AppInfo } from '@tft/shared-types/ipc'
import { analyzeCaptureInputSchema } from '@tft/shared-types/recognition'
import { appSettingsPatchSchema } from '@tft/shared-types/settings'
import { isPathInside, resolveCaptureDirectory } from './capture/capture-paths'
import type { CaptureService } from './capture/capture-service'
import { errorMessage } from './errors'
import type { Logger } from './logger'
import { resolveSetCatalogPath } from './recognition/catalog'
import type { SettingsStore } from './settings-store'
import type { WorkerSupervisor } from './worker/worker-supervisor'

interface IpcDependencies {
  settings: SettingsStore
  supervisor: WorkerSupervisor
  capture: CaptureService
  logger: Logger
  userDataPath: string
  recognitionDir: string | null
  smokeTest: boolean
}

const sourceIdSchema = z.string().min(1)
const capturePathSchema = z.string().min(1)
const tailRequestSchema = z.number().int().min(1).max(2000).optional()

export function registerIpcHandlers(dependencies: IpcDependencies): () => void {
  const channels: Array<[string, (payload: unknown) => unknown | Promise<unknown>]> = [
    [
      IPC_CHANNELS.settingsGet,
      () => {
        return dependencies.settings.get()
      },
    ],
    [
      IPC_CHANNELS.settingsUpdate,
      (payload) => {
        const patch = appSettingsPatchSchema.parse(payload ?? {})
        const next = dependencies.settings.update(patch)
        dependencies.logger.info('settings.updated', { patch })
        return next
      },
    ],
    [
      IPC_CHANNELS.captureListSources,
      () => {
        return dependencies.capture.listSources()
      },
    ],
    [
      IPC_CHANNELS.captureSelectSource,
      (payload) => {
        const sourceId = sourceIdSchema.parse(payload)
        dependencies.capture.selectSource(sourceId)
        return null
      },
    ],
    [
      IPC_CHANNELS.captureSaveFrame,
      (payload) => {
        return dependencies.capture.saveFrame(payload)
      },
    ],
    [
      IPC_CHANNELS.captureReveal,
      (payload) => {
        const filePath = capturePathSchema.parse(payload)
        dependencies.capture.revealCapture(filePath)
        return null
      },
    ],
    [
      IPC_CHANNELS.recognitionAnalyze,
      async (payload) => {
        const input = analyzeCaptureInputSchema.parse(payload)
        const captureDirectory = resolveCaptureDirectory(
          dependencies.settings.get().capture.saveDirectory,
          dependencies.userDataPath,
        )
        const imagePath = resolve(input.filePath)

        // The renderer may only analyze captures the app itself wrote.
        if (!isPathInside(captureDirectory, imagePath)) {
          throw new Error('Recognition is limited to files inside the capture directory.')
        }
        if (!existsSync(imagePath)) {
          throw new Error(`Capture file not found: ${imagePath}`)
        }

        const setId = input.setId ?? undefined
        const catalog = resolveSetCatalogPath(dependencies.recognitionDir, setId)
        if (!catalog) {
          throw new Error(`No recognition catalog is available for set ${setId ?? 'set-18'}.`)
        }

        if (dependencies.supervisor.getStatus().state !== 'running') {
          dependencies.logger.info('recognition.worker-auto-start')
        }
        await dependencies.supervisor.ensureRunning()

        dependencies.logger.info('recognition.analyze', {
          imagePath,
          setId: setId ?? 'set-18',
          catalogPath: catalog.path,
          catalogOrigin: catalog.origin,
        })

        return dependencies.supervisor.analyze({
          imagePath,
          captureTimestamp: input.captureTimestamp,
          crop: input.crop,
          catalogPath: catalog.path,
          ...(setId ? { setId } : {}),
          ...(input.preprocessMode ? { preprocessMode: input.preprocessMode } : {}),
          ...(input.minConfidence !== undefined ? { minConfidence: input.minConfidence } : {}),
          ...(input.minOcrConfidence !== undefined
            ? { minOcrConfidence: input.minOcrConfidence }
            : {}),
        })
      },
    ],
    [
      IPC_CHANNELS.workerGetStatus,
      () => {
        return dependencies.supervisor.getStatus()
      },
    ],
    [
      IPC_CHANNELS.workerStart,
      () => {
        return dependencies.supervisor.start()
      },
    ],
    [
      IPC_CHANNELS.workerStop,
      () => {
        return dependencies.supervisor.stop('user-stopped')
      },
    ],
    [
      IPC_CHANNELS.workerRestart,
      () => {
        return dependencies.supervisor.restart()
      },
    ],
    [
      IPC_CHANNELS.logsTail,
      (payload) => {
        const maxLines = tailRequestSchema.parse(payload)
        return dependencies.logger.tail(maxLines ?? 200)
      },
    ],
    [
      IPC_CHANNELS.logsReveal,
      () => {
        shell.showItemInFolder(dependencies.logger.filePath)
        return null
      },
    ],
    [
      IPC_CHANNELS.appGetInfo,
      () => {
        return buildAppInfo(dependencies)
      },
    ],
    [
      IPC_CHANNELS.appOpenUserData,
      async () => {
        const error = await shell.openPath(dependencies.userDataPath)
        if (error) {
          throw new Error(error)
        }
        return null
      },
    ],
  ]

  for (const [channel, handler] of channels) {
    ipcMain.handle(channel, async (_event, payload: unknown) => {
      try {
        return await handler(payload)
      } catch (error) {
        const message = errorMessage(error)
        dependencies.logger.warn('ipc.error', { channel, message })
        throw new Error(message, { cause: error })
      }
    })
  }

  return () => {
    for (const [channel] of channels) {
      ipcMain.removeHandler(channel)
    }
  }
}

function buildAppInfo(dependencies: IpcDependencies): AppInfo {
  return {
    name: 'TFT Soundtrack Companion',
    version: app.getVersion(),
    electron: process.versions.electron ?? 'unknown',
    chrome: process.versions.chrome ?? 'unknown',
    node: process.versions.node ?? 'unknown',
    platform: process.platform,
    arch: process.arch,
    userDataPath: dependencies.userDataPath,
    capturesPath: resolveCaptureDirectory(
      dependencies.settings.get().capture.saveDirectory,
      dependencies.userDataPath,
    ),
    logsPath: dependencies.logger.filePath,
    recognitionDir: dependencies.recognitionDir,
    smokeTest: dependencies.smokeTest,
  }
}
