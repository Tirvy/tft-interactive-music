import { randomUUID } from 'node:crypto'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import {
  desktopCapturer,
  screen,
  shell,
  type BrowserWindow,
  type DesktopCapturerSource,
  type Display,
  type Session,
  type WebContents,
} from 'electron'
import {
  saveCaptureRequestSchema,
  type CaptureDisplay,
  type CaptureSource,
  type SavedCapture,
} from '@tft/shared-types/capture'
import type { Logger } from '../logger'
import type { SettingsStore } from '../settings-store'
import { captureFileName, isPathInside, resolveCaptureDirectory } from './capture-paths'

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])

interface CaptureServiceOptions {
  userDataPath: string
  settings: SettingsStore
  logger: Logger
  getMainWindow: () => BrowserWindow | null
}

export class CaptureService {
  private selectedSourceId: string | null = null

  constructor(private readonly options: CaptureServiceOptions) {}

  async listSources(): Promise<CaptureSource[]> {
    const sources = await desktopCapturer.getSources({
      types: ['screen', 'window'],
      thumbnailSize: { width: 480, height: 270 },
      fetchWindowIcons: true,
    })
    const displays = screen.getAllDisplays()

    return sources
      .map((source) => this.toCaptureSource(source, displays))
      .sort((left, right) => {
        if (left.type !== right.type) {
          return left.type === 'screen' ? -1 : 1
        }
        return left.name.localeCompare(right.name)
      })
  }

  selectSource(sourceId: string): void {
    this.selectedSourceId = sourceId
  }

  saveFrame(input: unknown): SavedCapture {
    const request = saveCaptureRequestSchema.parse(input)
    const directory = this.getCaptureDirectory()
    mkdirSync(directory, { recursive: true })

    const bytes = Buffer.from(
      request.bytes.buffer,
      request.bytes.byteOffset,
      request.bytes.byteLength,
    )

    if (
      bytes.byteLength < PNG_MAGIC.length ||
      !bytes.subarray(0, PNG_MAGIC.length).equals(PNG_MAGIC)
    ) {
      throw new Error('Capture payload is not a PNG image.')
    }

    const id = randomUUID()
    const fileName = captureFileName(request.sourceName, request.capturedAt, id)
    const filePath = join(directory, fileName)

    writeFileSync(filePath, bytes, { flag: 'wx' })

    const saved: SavedCapture = {
      id,
      fileName,
      filePath,
      byteLength: bytes.byteLength,
      width: request.width,
      height: request.height,
      sourceId: request.sourceId,
      sourceName: request.sourceName,
      capturedAt: request.capturedAt,
      displayScaleFactor: request.displayScaleFactor,
      sourceWidth: request.sourceWidth,
      sourceHeight: request.sourceHeight,
    }

    this.options.logger.info('capture.saved', {
      filePath,
      width: saved.width,
      height: saved.height,
      sourceId: saved.sourceId,
      displayScaleFactor: saved.displayScaleFactor,
    })

    return saved
  }

  revealCapture(filePath: string): void {
    const resolvedPath = resolve(filePath)
    const allowedDirectories = [
      this.getCaptureDirectory(),
      resolveCaptureDirectory(null, this.options.userDataPath),
    ]

    if (!allowedDirectories.some((directory) => isPathInside(directory, resolvedPath))) {
      throw new Error('Refusing to reveal a file outside the capture directory.')
    }

    shell.showItemInFolder(resolvedPath)
  }

  installSessionHandlers(
    session: Session,
    isTrustedSender: (webContents: WebContents | null) => boolean,
  ): void {
    session.setPermissionRequestHandler((webContents, permission, callback) => {
      callback(permission === 'display-capture' && isTrustedSender(webContents))
    })

    session.setPermissionCheckHandler((webContents, permission) => {
      return permission === 'display-capture' && isTrustedSender(webContents)
    })

    session.setDisplayMediaRequestHandler(
      async (_request, callback) => {
        try {
          const sources = await desktopCapturer.getSources({ types: ['screen', 'window'] })
          const selected = this.selectedSourceId
            ? sources.find((source) => source.id === this.selectedSourceId)
            : undefined
          const source =
            selected ??
            sources.find((candidate) => candidate.id.startsWith('screen:')) ??
            sources.at(0)

          if (!source) {
            this.options.logger.warn('capture.no-display-media-source')
            callback({})
            return
          }

          this.options.logger.info('capture.display-media', {
            sourceId: source.id,
            name: source.name,
          })
          callback({ video: source })
        } catch (error) {
          this.options.logger.error('capture.display-media-failed', {
            message: error instanceof Error ? error.message : String(error),
          })
          callback({})
        }
      },
      { useSystemPicker: false },
    )
  }

  private getCaptureDirectory(): string {
    const configured = this.options.settings.get().capture.saveDirectory
    return resolveCaptureDirectory(configured, this.options.userDataPath)
  }

  private toCaptureSource(source: DesktopCapturerSource, displays: Display[]): CaptureSource {
    const display = resolveDisplayForSource(source, displays)

    return {
      id: source.id,
      name: source.name,
      type: source.id.startsWith('screen:') ? 'screen' : 'window',
      displayId: display ? String(display.id) : null,
      display: display ? toCaptureDisplay(display) : null,
      thumbnailDataUrl: source.thumbnail.isEmpty() ? null : source.thumbnail.toDataURL(),
      appIconDataUrl:
        source.appIcon && !source.appIcon.isEmpty() ? source.appIcon.toDataURL() : null,
    }
  }
}

/**
 * Match a desktopCapturer source to an Electron Display.
 *
 * Windows screen sources sometimes report an empty `display_id` and use a
 * compact `screen:<index>:0` id instead of the Electron display id. Try the
 * explicit id, then the source id, then the source index, and finally the
 * primary display when only one display exists.
 */
function resolveDisplayForSource(
  source: DesktopCapturerSource,
  displays: Display[],
): Display | null {
  if (source.display_id) {
    const explicit = displays.find((display) => String(display.id) === source.display_id)
    if (explicit) {
      return explicit
    }
  }

  if (!source.id.startsWith('screen:')) {
    return null
  }

  const segment = source.id.split(':')[1]
  if (!segment) {
    return null
  }

  const byId = displays.find((display) => String(display.id) === segment)
  if (byId) {
    return byId
  }

  const index = Number.parseInt(segment, 10)
  if (Number.isInteger(index) && index >= 0 && index < displays.length) {
    return displays[index] ?? null
  }

  return displays.length === 1 ? (displays[0] ?? null) : null
}

function toCaptureDisplay(display: Display): CaptureDisplay {
  return {
    id: String(display.id),
    label: display.label,
    size: { ...display.size },
    workArea: { ...display.workArea },
    physicalSize: {
      width: Math.round(display.size.width * display.scaleFactor),
      height: Math.round(display.size.height * display.scaleFactor),
    },
    scaleFactor: display.scaleFactor,
    rotation: display.rotation,
    internal: display.internal,
  }
}
