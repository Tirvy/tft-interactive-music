import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import { IPC_CHANNELS, type TftApi } from '@tft/shared-types/ipc'
import type { AppSettingsPatch } from '@tft/shared-types/settings'
import type { WorkerStatus } from '@tft/shared-types/worker'

const api: TftApi = {
  settings: {
    get: () => ipcRenderer.invoke(IPC_CHANNELS.settingsGet),
    update: (patch: AppSettingsPatch) => ipcRenderer.invoke(IPC_CHANNELS.settingsUpdate, patch),
  },
  capture: {
    listSources: () => ipcRenderer.invoke(IPC_CHANNELS.captureListSources),
    selectSource: (sourceId: string) =>
      ipcRenderer.invoke(IPC_CHANNELS.captureSelectSource, sourceId),
    saveFrame: (request) => ipcRenderer.invoke(IPC_CHANNELS.captureSaveFrame, request),
    revealCapture: (filePath: string) => ipcRenderer.invoke(IPC_CHANNELS.captureReveal, filePath),
  },
  recognition: {
    analyze: (input) => ipcRenderer.invoke(IPC_CHANNELS.recognitionAnalyze, input),
  },
  worker: {
    getStatus: () => ipcRenderer.invoke(IPC_CHANNELS.workerGetStatus),
    start: () => ipcRenderer.invoke(IPC_CHANNELS.workerStart),
    stop: () => ipcRenderer.invoke(IPC_CHANNELS.workerStop),
    restart: () => ipcRenderer.invoke(IPC_CHANNELS.workerRestart),
    onStatus: (listener: (status: WorkerStatus) => void) => {
      const handler = (_event: IpcRendererEvent, status: WorkerStatus): void => {
        listener(status)
      }

      ipcRenderer.on(IPC_CHANNELS.workerStatus, handler)
      return () => {
        ipcRenderer.removeListener(IPC_CHANNELS.workerStatus, handler)
      }
    },
  },
  logs: {
    tail: (maxLines?: number) => ipcRenderer.invoke(IPC_CHANNELS.logsTail, maxLines),
    reveal: () => ipcRenderer.invoke(IPC_CHANNELS.logsReveal),
  },
  app: {
    getInfo: () => ipcRenderer.invoke(IPC_CHANNELS.appGetInfo),
    openUserData: () => ipcRenderer.invoke(IPC_CHANNELS.appOpenUserData),
  },
}

contextBridge.exposeInMainWorld('tft', api)
