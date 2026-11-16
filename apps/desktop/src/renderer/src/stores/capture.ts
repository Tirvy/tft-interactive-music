import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'
import type { CaptureSource, NormalizedRect, SavedCapture } from '@tft/shared-types/capture'
import type { RecognitionResultMessage } from '@tft/shared-types/protocol'
import { DisplayCaptureSession, type CaptureSessionStats } from '../services/capture-session'
import { errorMessage } from '../utils/errors'
import { useSettingsStore } from './settings'

export interface CaptureStats extends CaptureSessionStats {
  measuredFps: number | null
  measuredAt: string | null
}

export const useCaptureStore = defineStore('capture', () => {
  const session = new DisplayCaptureSession()

  const sources = ref<CaptureSource[]>([])
  const selectedId = ref<string | null>(null)
  const loadingSources = ref(false)
  const stream = shallowRef<MediaStream | null>(null)
  const streaming = ref(false)
  const saving = ref(false)
  const measuring = ref(false)
  const stats = ref<CaptureStats | null>(null)
  const lastCapture = ref<SavedCapture | null>(null)
  const error = ref<string | null>(null)

  /**
   * The trait panel occupies the upper-left portion of the TFT window. This
   * default comes from the Set 18 reference screenshot and stays editable
   * until crop calibration is automated.
   */
  const crop = ref<NormalizedRect>({ x: 0, y: 0.2, width: 0.16, height: 0.5 })
  const analyzing = ref(false)
  const lastRecognition = ref<RecognitionResultMessage | null>(null)
  const recognitionError = ref<string | null>(null)

  const cropValid = computed(() => {
    const rect = crop.value
    const values = [rect.x, rect.y, rect.width, rect.height]
    return (
      values.every((value) => Number.isFinite(value)) &&
      rect.x >= 0 &&
      rect.y >= 0 &&
      rect.width > 0 &&
      rect.height > 0 &&
      rect.x + rect.width <= 1 &&
      rect.y + rect.height <= 1
    )
  })

  const selectedSource = computed(
    () => sources.value.find((source) => source.id === selectedId.value) ?? null,
  )

  async function loadSources(): Promise<void> {
    loadingSources.value = true
    error.value = null

    try {
      sources.value = await window.tft.capture.listSources()

      const settingsStore = useSettingsStore()
      const preferredId = settingsStore.settings.capture.preferredSourceId
      const preferred = sources.value.find((source) => source.id === preferredId)

      selectedId.value =
        preferred?.id ??
        sources.value.find((source) => source.type === 'screen')?.id ??
        sources.value[0]?.id ??
        null
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      loadingSources.value = false
    }
  }

  async function selectSource(sourceId: string): Promise<void> {
    if (streaming.value) {
      stopPreview()
    }

    selectedId.value = sourceId
    const source = sources.value.find((candidate) => candidate.id === sourceId)

    try {
      const settingsStore = useSettingsStore()
      await settingsStore.update({
        capture: {
          preferredSourceId: sourceId,
          preferredSourceName: source?.name ?? null,
        },
      })
    } catch {
      // The settings store already exposes the error; source selection in the
      // current session still works.
    }
  }

  async function startPreview(): Promise<void> {
    if (!selectedId.value) {
      error.value = 'Select a capture source first.'
      return
    }

    error.value = null

    try {
      const settingsStore = useSettingsStore()
      await window.tft.capture.selectSource(selectedId.value)
      const result = await session.start(settingsStore.settings.capture.frameRate)

      stream.value = result.stream
      streaming.value = true
      stats.value = {
        ...result.stats,
        measuredFps: null,
        measuredAt: null,
      }

      const activeStream = result.stream
      for (const track of activeStream.getVideoTracks()) {
        track.addEventListener(
          'ended',
          () => {
            if (stream.value !== activeStream) {
              return
            }
            stream.value = null
            streaming.value = false
          },
          { once: true },
        )
      }
    } catch (cause) {
      error.value = errorMessage(cause)
      stopPreview()
    }
  }

  function stopPreview(): void {
    stream.value = null
    streaming.value = false
    session.stop()
  }

  async function captureFrom(video: HTMLVideoElement): Promise<SavedCapture | null> {
    const source = selectedSource.value

    if (!source) {
      error.value = 'Select a capture source first.'
      return null
    }

    if (!streaming.value) {
      error.value = 'Start the capture preview before saving a frame.'
      return null
    }

    saving.value = true
    error.value = null

    try {
      const frame = await session.grabPng(video)
      const saved = await window.tft.capture.saveFrame({
        bytes: frame.bytes,
        width: frame.width,
        height: frame.height,
        sourceId: source.id,
        sourceName: source.name,
        capturedAt: new Date().toISOString(),
        displayScaleFactor: source.display?.scaleFactor ?? null,
        sourceWidth: source.display?.physicalSize.width ?? null,
        sourceHeight: source.display?.physicalSize.height ?? null,
      })

      lastCapture.value = saved
      lastRecognition.value = null
      recognitionError.value = null
      return saved
    } catch (cause) {
      error.value = errorMessage(cause)
      return null
    } finally {
      saving.value = false
    }
  }

  async function measureFrameRate(video: HTMLVideoElement): Promise<void> {
    if (!streaming.value) {
      return
    }

    measuring.value = true
    error.value = null

    try {
      const fps = await session.measureFrameRate(video, 3000)

      if (stats.value) {
        stats.value = {
          ...stats.value,
          measuredFps: Math.round(fps * 10) / 10,
          measuredAt: new Date().toISOString(),
        }
      }
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      measuring.value = false
    }
  }

  async function revealLastCapture(): Promise<void> {
    if (!lastCapture.value) {
      return
    }

    try {
      await window.tft.capture.revealCapture(lastCapture.value.filePath)
    } catch (cause) {
      error.value = errorMessage(cause)
    }
  }

  async function analyzeLastCapture(): Promise<RecognitionResultMessage | null> {
    const capture = lastCapture.value
    if (!capture) {
      recognitionError.value = 'Capture and save a frame before running recognition.'
      return null
    }

    if (!cropValid.value) {
      recognitionError.value = 'The crop must be inside the frame and larger than zero.'
      return null
    }

    analyzing.value = true
    recognitionError.value = null

    try {
      const result = await window.tft.recognition.analyze({
        filePath: capture.filePath,
        captureTimestamp: capture.capturedAt,
        crop: { ...crop.value },
        setId: 'set-18',
      })

      lastRecognition.value = result
      return result
    } catch (cause) {
      recognitionError.value = errorMessage(cause)
      return null
    } finally {
      analyzing.value = false
    }
  }

  function dispose(): void {
    stopPreview()
  }

  return {
    sources,
    selectedId,
    selectedSource,
    loadingSources,
    stream,
    streaming,
    saving,
    measuring,
    stats,
    lastCapture,
    error,
    crop,
    cropValid,
    analyzing,
    lastRecognition,
    recognitionError,
    loadSources,
    selectSource,
    startPreview,
    stopPreview,
    captureFrom,
    measureFrameRate,
    revealLastCapture,
    analyzeLastCapture,
    dispose,
  }
})
