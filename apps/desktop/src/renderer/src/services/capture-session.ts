export interface CaptureFrame {
  bytes: Uint8Array<ArrayBuffer>
  width: number
  height: number
}

export interface CaptureSessionStats {
  width: number
  height: number
  frameRate: number | null
  displaySurface: string | null
  trackLabel: string
}

type FrameRequestVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (callback: (now: number) => void) => number
}

/**
 * Thin wrapper around `getDisplayMedia` and canvas frame extraction.
 * Source selection and file saving stay in the Electron main process; this
 * module only owns browser-bound capture plumbing.
 */
export class DisplayCaptureSession {
  private stream: MediaStream | null = null

  async start(frameRate: number): Promise<{ stream: MediaStream; stats: CaptureSessionStats }> {
    this.stop()

    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        frameRate: { ideal: frameRate, max: frameRate },
      },
      audio: false,
    })

    const track = stream.getVideoTracks()[0]
    if (!track) {
      stream.getTracks().forEach((candidate) => candidate.stop())
      throw new Error('The capture source returned no video track.')
    }

    const settings = track.getSettings()
    this.stream = stream

    return {
      stream,
      stats: {
        width: settings.width ?? 0,
        height: settings.height ?? 0,
        frameRate: settings.frameRate ?? null,
        displaySurface: settings.displaySurface ?? null,
        trackLabel: track.label,
      },
    }
  }

  stop(): void {
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
  }

  async grabPng(video: HTMLVideoElement): Promise<CaptureFrame> {
    const width = video.videoWidth
    const height = video.videoHeight

    if (width === 0 || height === 0) {
      throw new Error('The capture preview has no frame yet.')
    }

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height

    const context = canvas.getContext('2d')
    if (!context) {
      throw new Error('Canvas 2D is unavailable in the renderer.')
    }

    context.drawImage(video, 0, 0, width, height)

    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((result) => {
        if (result) {
          resolve(result)
        } else {
          reject(new Error('Failed to encode the capture frame as PNG.'))
        }
      }, 'image/png')
    })

    return {
      bytes: new Uint8Array(await blob.arrayBuffer()),
      width,
      height,
    }
  }

  async measureFrameRate(video: HTMLVideoElement, durationMs = 3000): Promise<number> {
    const frameVideo = video as FrameRequestVideo

    if (typeof frameVideo.requestVideoFrameCallback === 'function') {
      return new Promise<number>((resolve, reject) => {
        const startedAt = performance.now()
        let frames = 0
        let firstFrameAt: number | null = null
        let lastFrameAt: number | null = null
        let finished = false

        const timeout = setTimeout(() => {
          if (!finished) {
            finished = true
            reject(new Error('Timed out waiting for video frames.'))
          }
        }, durationMs + 2000)

        const finish = (): void => {
          if (finished) {
            return
          }
          finished = true
          clearTimeout(timeout)

          const elapsedSeconds =
            firstFrameAt !== null && lastFrameAt !== null ? (lastFrameAt - firstFrameAt) / 1000 : 0

          resolve(elapsedSeconds > 0 ? Math.max(0, frames - 1) / elapsedSeconds : 0)
        }

        const onFrame = (now: number): void => {
          if (finished) {
            return
          }

          if (firstFrameAt === null) {
            firstFrameAt = now
          }
          lastFrameAt = now
          frames += 1

          if (now - startedAt < durationMs) {
            frameVideo.requestVideoFrameCallback?.(onFrame)
          } else {
            finish()
          }
        }

        frameVideo.requestVideoFrameCallback?.(onFrame)
      })
    }

    return new Promise<number>((resolve) => {
      const startedAt = performance.now()
      let frames = 0

      const tick = (): void => {
        frames += 1
        const now = performance.now()

        if (now - startedAt < durationMs) {
          requestAnimationFrame(tick)
        } else {
          resolve(frames / ((now - startedAt) / 1000))
        }
      }

      requestAnimationFrame(tick)
    })
  }
}
