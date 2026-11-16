import { randomUUID } from 'node:crypto'
import { copyFileSync, mkdirSync, unlinkSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { app, BrowserWindow, session } from 'electron'
import { IPC_CHANNELS } from '@tft/shared-types/ipc'
import { errorMessage } from './errors'
import { Logger } from './logger'
import { findRecognitionDir } from './paths'
import { SettingsStore } from './settings-store'
import { resolveCaptureDirectory } from './capture/capture-paths'
import { CaptureService } from './capture/capture-service'
import { registerIpcHandlers } from './ipc'
import { WorkerSupervisor } from './worker/worker-supervisor'

const smokeTest = process.argv.includes('--smoke-test')
const captureSmokeTest = process.argv.includes('--capture-smoke-test')
const recognitionSmokeTest = process.argv.includes('--recognition-smoke-test')

app.setName('TFT Soundtrack Companion')

let mainWindow: BrowserWindow | null = null
let logger: Logger | null = null
let supervisor: WorkerSupervisor | null = null
let cleanupIpc: (() => void) | null = null
let shuttingDown = false

process.on('uncaughtException', (error) => {
  logger?.error('process.uncaught-exception', {
    message: errorMessage(error),
    stack: error.stack,
  })
})

process.on('unhandledRejection', (reason) => {
  logger?.error('process.unhandled-rejection', { message: errorMessage(reason) })
})

const hasSingleInstanceLock = app.requestSingleInstanceLock()
if (!hasSingleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore()
      }
      mainWindow.show()
      mainWindow.focus()
    }
  })

  app.whenReady().then(() => {
    void bootstrap()
  })

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      void shutdown()
    }
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })

  app.on('before-quit', (event) => {
    if (!shuttingDown && supervisor?.isActive()) {
      event.preventDefault()
      void shutdown()
    }
  })
}

async function bootstrap(): Promise<void> {
  app.setAppUserModelId('com.tft.soundtrack')

  const userDataPath = app.getPath('userData')
  const appLogger = new Logger(resolve(userDataPath, 'logs'), { mirrorToConsole: !app.isPackaged })
  logger = appLogger

  const settingsStore = new SettingsStore(resolve(userDataPath, 'settings.json'), appLogger)
  settingsStore.load()

  const recognitionDir = findRecognitionDir([
    app.getAppPath(),
    process.cwd(),
    resolve(__dirname, '../..'),
  ])

  appLogger.info('app.starting', {
    version: app.getVersion(),
    userDataPath,
    recognitionDir,
    smokeTest,
  })

  const captures = new CaptureService({
    userDataPath,
    settings: settingsStore,
    logger: appLogger,
    getMainWindow: () => mainWindow,
  })

  supervisor = new WorkerSupervisor({
    recognitionDir,
    logger: appLogger,
    getSettings: () => settingsStore.get(),
    onStatus: (status) => {
      for (const window of BrowserWindow.getAllWindows()) {
        if (!window.isDestroyed()) {
          window.webContents.send(IPC_CHANNELS.workerStatus, status)
        }
      }
    },
  })

  cleanupIpc = registerIpcHandlers({
    settings: settingsStore,
    supervisor,
    capture: captures,
    logger: appLogger,
    userDataPath,
    recognitionDir,
    smokeTest: smokeTest || captureSmokeTest || recognitionSmokeTest,
  })

  createWindow()
  captures.installSessionHandlers(session.defaultSession, (webContents) => {
    return webContents !== null && webContents.id === mainWindow?.webContents.id
  })

  if (settingsStore.get().worker.autoStart) {
    void supervisor.start()
  }

  if (smokeTest) {
    runSmokeTest()
  } else if (captureSmokeTest) {
    runCaptureSmokeTest()
  } else if (recognitionSmokeTest) {
    runRecognitionSmokeTest(
      recognitionDir,
      resolveCaptureDirectory(settingsStore.get().capture.saveDirectory, userDataPath),
    )
  }
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1024,
    minHeight: 680,
    show: false,
    backgroundColor: '#0d1117',
    title: 'TFT Soundtrack Companion',
    webPreferences: {
      preload: resolve(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  })

  mainWindow.setMenuBarVisibility(false)
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  mainWindow.webContents.on('before-input-event', (_event, input) => {
    if (input.type === 'keyDown' && input.key === 'F12') {
      mainWindow?.webContents.toggleDevTools()
    }
  })

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  const devServerUrl = process.env['ELECTRON_RENDERER_URL']
  if (devServerUrl) {
    void mainWindow.loadURL(devServerUrl)
  } else {
    void mainWindow.loadFile(resolve(__dirname, '../renderer/index.html'))
  }
}

function runSmokeTest(): void {
  const window = mainWindow
  if (!window) {
    console.error('SMOKE_FAIL: main window was not created')
    app.exit(1)
    return
  }

  const timeout = setTimeout(() => {
    console.error('SMOKE_FAIL: timed out waiting for the renderer')
    app.exit(1)
  }, 25_000)

  window.webContents.once('did-finish-load', () => {
    void (async () => {
      try {
        await delay(500)
        const mountedChildren = await window.webContents.executeJavaScript(
          'document.querySelector("#app")?.childElementCount ?? 0',
        )
        const url = window.webContents.getURL()
        console.log(
          JSON.stringify({
            event: 'smoke-test',
            ok: mountedChildren > 0,
            mountedChildren,
            url,
          }),
        )
        clearTimeout(timeout)
        await finishSmokeTest(mountedChildren > 0 ? 0 : 2)
      } catch (error) {
        clearTimeout(timeout)
        console.error(`SMOKE_FAIL: ${errorMessage(error)}`)
        await finishSmokeTest(1)
      }
    })()
  })
}

/**
 * Diagnostic mode: capture the primary screen through the same preload,
 * getDisplayMedia handler, canvas encoder, and IPC save path used by the UI.
 * This exists so the capture spike can be verified without manual input.
 */
function runCaptureSmokeTest(): void {
  const window = mainWindow
  if (!window) {
    console.error('CAPTURE_SMOKE_FAIL: main window was not created')
    app.exit(1)
    return
  }

  const timeout = setTimeout(() => {
    console.error('CAPTURE_SMOKE_FAIL: timed out waiting for the renderer')
    app.exit(1)
  }, 30_000)

  window.webContents.once('did-finish-load', () => {
    void (async () => {
      try {
        await delay(500)
        const result: unknown = await window.webContents.executeJavaScript(
          CAPTURE_SMOKE_SCRIPT,
          true,
        )
        clearTimeout(timeout)
        console.log(JSON.stringify({ event: 'capture-smoke-test', ok: true, result }))
        await finishSmokeTest(0)
      } catch (error) {
        clearTimeout(timeout)
        console.error(`CAPTURE_SMOKE_FAIL: ${errorMessage(error)}`)
        await finishSmokeTest(1)
      }
    })()
  })
}

/**
 * Diagnostic mode: save a known TFT screenshot through the same capture-path
 * rules, then run the real recognition chain (preload -> IPC -> supervisor ->
 * Python worker). The temporary capture is deleted afterwards.
 */
function runRecognitionSmokeTest(recognitionDir: string | null, captureDirectory: string): void {
  const window = mainWindow
  if (!window) {
    console.error('RECOGNITION_SMOKE_FAIL: main window was not created')
    app.exit(1)
    return
  }

  if (!recognitionDir) {
    console.error('RECOGNITION_SMOKE_FAIL: recognition directory was not found')
    app.exit(1)
    return
  }

  const fixturePath = join(recognitionDir, '..', '..', 'tests', 'ru', 'screenshot-1.png')
  const imagePath = join(captureDirectory, `tft-capture-recognition-smoke-${randomUUID()}.png`)

  const removeImage = (): void => {
    try {
      unlinkSync(imagePath)
    } catch {
      // The smoke run may fail before the copy exists.
    }
  }

  const timeout = setTimeout(() => {
    removeImage()
    console.error('RECOGNITION_SMOKE_FAIL: timed out waiting for the worker')
    app.exit(1)
  }, 420_000)

  window.webContents.once('did-finish-load', () => {
    void (async () => {
      try {
        mkdirSync(captureDirectory, { recursive: true })
        copyFileSync(fixturePath, imagePath)
        await delay(500)

        const request = {
          filePath: imagePath,
          captureTimestamp: new Date().toISOString(),
          crop: { x: 0, y: 0.2, width: 0.16, height: 0.5 },
          setId: 'set-18',
        }
        const result: unknown = await window.webContents.executeJavaScript(
          `window.tft.recognition.analyze(${JSON.stringify(request)})`,
          true,
        )

        const response = result as { type?: string; status?: string; traits?: unknown }
        if (response.type !== 'recognition.result' || !Array.isArray(response.traits)) {
          throw new Error('The renderer did not receive a recognition result.')
        }

        removeImage()
        clearTimeout(timeout)
        console.log(JSON.stringify({ event: 'recognition-smoke-test', ok: true, result }))
        await finishSmokeTest(0)
      } catch (error) {
        removeImage()
        clearTimeout(timeout)
        console.error(`RECOGNITION_SMOKE_FAIL: ${errorMessage(error)}`)
        await finishSmokeTest(1)
      }
    })()
  })
}

async function finishSmokeTest(exitCode: number): Promise<void> {
  shuttingDown = true
  await supervisor?.stop('smoke-test')
  supervisor?.dispose()
  cleanupIpc?.()
  app.exit(exitCode)
}

const CAPTURE_SMOKE_SCRIPT = `
(async () => {
  const sources = await window.tft.capture.listSources()
  const source = sources.find((candidate) => candidate.type === 'screen') ?? sources[0]
  if (!source) {
    throw new Error('No capture source was returned.')
  }

  await window.tft.capture.selectSource(source.id)

  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: { frameRate: { ideal: 2, max: 5 } },
    audio: false,
  })

  try {
    const track = stream.getVideoTracks()[0]
    if (!track) {
      throw new Error('No video track was returned.')
    }

    const video = document.createElement('video')
    video.muted = true
    video.playsInline = true
    video.srcObject = stream

    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Video metadata timed out.')), 10000)
      video.onloadedmetadata = () => {
        clearTimeout(timer)
        resolve()
      }
      video.onerror = () => {
        clearTimeout(timer)
        reject(new Error('The capture video element failed.'))
      }
    })

    await video.play()
    await new Promise((resolve) => setTimeout(resolve, 600))

    const width = video.videoWidth
    const height = video.videoHeight
    if (!width || !height) {
      throw new Error('The capture element reported an empty frame.')
    }

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    if (!context) {
      throw new Error('Canvas 2D is unavailable.')
    }
    context.drawImage(video, 0, 0, width, height)

    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(
        (result) => (result ? resolve(result) : reject(new Error('PNG encoding failed.'))),
        'image/png',
      )
    })
    const bytes = new Uint8Array(await blob.arrayBuffer())

    const saved = await window.tft.capture.saveFrame({
      bytes,
      width,
      height,
      sourceId: source.id,
      sourceName: source.name,
      capturedAt: new Date().toISOString(),
      displayScaleFactor: source.display?.scaleFactor ?? null,
      sourceWidth: source.display?.physicalSize.width ?? null,
      sourceHeight: source.display?.physicalSize.height ?? null,
    })

    return { sourceId: source.id, sourceName: source.name, width, height, saved }
  } finally {
    stream.getTracks().forEach((track) => track.stop())
  }
})()
`

async function shutdown(): Promise<void> {
  if (shuttingDown) {
    return
  }

  shuttingDown = true

  try {
    await supervisor?.stop('app-quit')
  } catch (error) {
    logger?.warn('app.shutdown-failed', { message: errorMessage(error) })
  } finally {
    supervisor?.dispose()
    cleanupIpc?.()
    logger?.info('app.quitting')
    app.quit()
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolveDelay) => {
    setTimeout(resolveDelay, milliseconds)
  })
}
