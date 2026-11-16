import type { CaptureSource, SavedCapture, SaveCaptureRequest } from './capture'
import type { AnalyzeCaptureInput } from './recognition'
import type { RecognitionResultMessage } from './protocol'
import type { AppSettings, AppSettingsPatch } from './settings'
import type { WorkerStatus } from './worker'

export const IPC_CHANNELS = {
  settingsGet: 'settings:get',
  settingsUpdate: 'settings:update',

  captureListSources: 'capture:list-sources',
  captureSelectSource: 'capture:select-source',
  captureSaveFrame: 'capture:save-frame',
  captureReveal: 'capture:reveal',
  recognitionAnalyze: 'recognition:analyze',

  workerGetStatus: 'worker:get-status',
  workerStart: 'worker:start',
  workerStop: 'worker:stop',
  workerRestart: 'worker:restart',
  workerStatus: 'worker:status',

  logsTail: 'logs:tail',
  logsReveal: 'logs:reveal',

  appGetInfo: 'app:get-info',
  appOpenUserData: 'app:open-user-data',
} as const

export type IpcChannel = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS]

export interface AppInfo {
  name: string
  version: string
  electron: string
  chrome: string
  node: string
  platform: string
  arch: string
  userDataPath: string
  capturesPath: string
  logsPath: string
  recognitionDir: string | null
  smokeTest: boolean
}

/**
 * The complete surface exposed on `window.tft` by the preload script.
 * Renderer code must go through this interface rather than importing
 * Electron or Node APIs.
 */
export interface TftApi {
  settings: {
    get(): Promise<AppSettings>
    update(patch: AppSettingsPatch): Promise<AppSettings>
  }
  capture: {
    listSources(): Promise<CaptureSource[]>
    selectSource(sourceId: string): Promise<void>
    saveFrame(request: SaveCaptureRequest): Promise<SavedCapture>
    revealCapture(filePath: string): Promise<void>
  }
  recognition: {
    analyze(input: AnalyzeCaptureInput): Promise<RecognitionResultMessage>
  }
  worker: {
    getStatus(): Promise<WorkerStatus>
    start(): Promise<WorkerStatus>
    stop(): Promise<WorkerStatus>
    restart(): Promise<WorkerStatus>
    onStatus(listener: (status: WorkerStatus) => void): () => void
  }
  logs: {
    tail(maxLines?: number): Promise<string[]>
    reveal(): Promise<void>
  }
  app: {
    getInfo(): Promise<AppInfo>
    openUserData(): Promise<void>
  }
}
