<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { NormalizedRect } from '@tft/shared-types/capture'
import { useCaptureStore } from '../stores/capture'

type SourceFilter = 'all' | 'screen' | 'window'

const capture = useCaptureStore()
const videoElement = ref<HTMLVideoElement | null>(null)
const filter = ref<SourceFilter>('all')
const query = ref('')

const cropFields: Array<{ key: keyof NormalizedRect; label: string }> = [
  { key: 'x', label: 'Left' },
  { key: 'y', label: 'Top' },
  { key: 'width', label: 'Width' },
  { key: 'height', label: 'Height' },
]

const filteredSources = computed(() => {
  const search = query.value.trim().toLowerCase()

  return capture.sources.filter((source) => {
    const matchesFilter = filter.value === 'all' || source.type === filter.value
    const matchesSearch = search.length === 0 || source.name.toLowerCase().includes(search)
    return matchesFilter && matchesSearch
  })
})

const displayDescription = computed(() => {
  const display = capture.selectedSource?.display
  if (!display) {
    return null
  }

  return `${display.size.width}×${display.size.height} DIP · ${display.physicalSize.width}×${display.physicalSize.height} physical · ${display.scaleFactor}× scale`
})

const recognitionMeta = computed(() => {
  const result = capture.lastRecognition
  if (!result) {
    return null
  }

  const diagnostics = result.diagnostics
  const elapsed = diagnostics['elapsedMs']
  const engine = diagnostics['ocrEngine']

  return {
    elapsed: typeof elapsed === 'number' ? `${Math.round(elapsed)} ms` : '—',
    engine: typeof engine === 'string' ? engine : '—',
  }
})

const diagnosticsJson = computed(() =>
  capture.lastRecognition ? JSON.stringify(capture.lastRecognition.diagnostics, null, 2) : '',
)

onMounted(() => {
  void capture.loadSources()
})

onBeforeUnmount(() => {
  capture.dispose()
})

watch(
  () => capture.stream,
  () => {
    attachStream()
  },
  { flush: 'post' },
)

function attachStream(): void {
  const video = videoElement.value
  if (!video) {
    return
  }

  if (video.srcObject !== capture.stream) {
    video.srcObject = capture.stream
  }

  if (capture.stream) {
    void video.play().catch(() => undefined)
  }
}

function selectSource(sourceId: string): void {
  void capture.selectSource(sourceId)
}

async function startPreview(): Promise<void> {
  await capture.startPreview()
  attachStream()
}

function stopPreview(): void {
  capture.stopPreview()
}

async function saveFrame(): Promise<void> {
  if (!videoElement.value) {
    return
  }

  await capture.captureFrom(videoElement.value)
}

async function measure(): Promise<void> {
  if (videoElement.value) {
    await capture.measureFrameRate(videoElement.value)
  }
}

async function analyze(): Promise<void> {
  await capture.analyzeLastCapture()
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  return `${(bytes / 1024).toFixed(1)} KB`
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Capture source</h1>
        <p>
          Enumerate screens and windows, preview the selected source, and save a full-resolution PNG
          for the capture spike. Source selection and file writes stay in the main process.
        </p>
      </div>
      <button
        type="button"
        class="button"
        :disabled="capture.loadingSources"
        @click="capture.loadSources()"
      >
        {{ capture.loadingSources ? 'Refreshing…' : 'Refresh sources' }}
      </button>
    </header>

    <div v-if="capture.error" class="alert" role="alert">
      <strong>Capture error</strong>
      <span>{{ capture.error }}</span>
    </div>

    <div class="capture-grid">
      <article class="panel source-panel">
        <div class="panel-heading">
          <div>
            <h2>Sources</h2>
            <p class="muted small">{{ capture.sources.length }} available</p>
          </div>
        </div>

        <div class="filter-row">
          <div class="segmented" role="group" aria-label="Source type filter">
            <button
              v-for="option in ['all', 'screen', 'window'] as SourceFilter[]"
              :key="option"
              type="button"
              :class="{ active: filter === option }"
              @click="filter = option"
            >
              {{ option }}
            </button>
          </div>
          <input v-model="query" type="search" placeholder="Filter by name" />
        </div>

        <div class="source-list">
          <button
            v-for="source in filteredSources"
            :key="source.id"
            type="button"
            class="source-item"
            :class="{ selected: source.id === capture.selectedId }"
            @click="selectSource(source.id)"
          >
            <img
              v-if="source.thumbnailDataUrl"
              class="source-thumb"
              :src="source.thumbnailDataUrl"
              alt=""
            />
            <span v-else class="source-thumb placeholder-thumb" />
            <span class="source-copy">
              <span class="source-title">
                <span class="type-pill">{{ source.type }}</span>
                {{ source.name }}
              </span>
              <small v-if="source.display">
                {{ source.display.size.width }}×{{ source.display.size.height }} @
                {{ source.display.scaleFactor }}×
              </small>
              <small v-else class="muted">Window source</small>
            </span>
          </button>

          <p v-if="filteredSources.length === 0" class="empty-state">
            No sources match the current filter.
          </p>
        </div>
      </article>

      <article class="panel preview-panel">
        <div class="panel-heading">
          <div>
            <h2>{{ capture.selectedSource?.name ?? 'No source selected' }}</h2>
            <p class="muted small">
              {{ displayDescription ?? 'Select a screen to see its DPI metadata.' }}
            </p>
          </div>
          <span class="pill" :class="{ ready: capture.streaming }">
            {{ capture.streaming ? 'Live' : 'Preview stopped' }}
          </span>
        </div>

        <div class="preview-stage">
          <video ref="videoElement" muted playsinline />
          <div v-if="!capture.streaming" class="preview-placeholder">
            <strong>No live preview</strong>
            <span>Select a source, then start the preview.</span>
          </div>
        </div>

        <div class="actions">
          <button
            type="button"
            class="button primary"
            :disabled="!capture.selectedId || capture.streaming"
            @click="startPreview"
          >
            Start preview
          </button>
          <button type="button" class="button" :disabled="!capture.streaming" @click="stopPreview">
            Stop
          </button>
          <button
            type="button"
            class="button"
            :disabled="!capture.streaming || capture.saving"
            @click="saveFrame"
          >
            {{ capture.saving ? 'Saving…' : 'Capture & save PNG' }}
          </button>
          <button
            type="button"
            class="button"
            :disabled="!capture.streaming || capture.measuring"
            @click="measure"
          >
            {{ capture.measuring ? 'Measuring…' : 'Measure 3 s' }}
          </button>
        </div>

        <dl v-if="capture.stats" class="details compact">
          <div>
            <dt>Video frame</dt>
            <dd>{{ capture.stats.width }}×{{ capture.stats.height }}</dd>
          </div>
          <div>
            <dt>Track frame rate</dt>
            <dd>{{ capture.stats.frameRate ?? 'not reported' }}</dd>
          </div>
          <div>
            <dt>Measured FPS</dt>
            <dd>{{ capture.stats.measuredFps ?? 'not measured' }}</dd>
          </div>
          <div>
            <dt>Display surface</dt>
            <dd>{{ capture.stats.displaySurface ?? 'not reported' }}</dd>
          </div>
          <div>
            <dt>Track label</dt>
            <dd>{{ capture.stats.trackLabel || '—' }}</dd>
          </div>
        </dl>

        <div v-if="capture.lastCapture" class="capture-result">
          <div>
            <strong>Saved {{ capture.lastCapture.fileName }}</strong>
            <small class="muted">
              {{ capture.lastCapture.width }}×{{ capture.lastCapture.height }} ·
              {{ formatBytes(capture.lastCapture.byteLength) }} ·
              {{ capture.lastCapture.capturedAt }}
            </small>
          </div>
          <code class="path">{{ capture.lastCapture.filePath }}</code>
          <button type="button" class="button subtle" @click="capture.revealLastCapture()">
            Show in folder
          </button>
        </div>

        <p v-else class="muted small">
          Capturing saves the current video frame as a PNG in the configured capture directory. The
          path and dimensions are recorded for the capture spike notes.
        </p>
      </article>
    </div>

    <article class="panel recognition-panel">
      <div class="panel-heading">
        <div>
          <h2>Trait recognition</h2>
          <p class="muted small">
            Analyze the saved capture with the Python worker. Crop values are fractions of the
            image, from 0 to 1.
          </p>
        </div>
        <span
          class="pill"
          :class="{
            ready: capture.lastRecognition?.status === 'ok',
            partial: capture.lastRecognition?.status === 'partial',
            error: capture.lastRecognition?.status === 'error',
          }"
        >
          {{ capture.lastRecognition?.status ?? 'no result' }}
        </span>
      </div>

      <div class="crop-grid">
        <label v-for="field in cropFields" :key="field.key">
          <span>{{ field.label }}</span>
          <input
            v-model.number="capture.crop[field.key]"
            type="number"
            min="0"
            max="1"
            step="0.01"
          />
        </label>
      </div>

      <div class="actions">
        <button
          type="button"
          class="button primary"
          :disabled="!capture.lastCapture || capture.analyzing || !capture.cropValid"
          @click="analyze"
        >
          {{ capture.analyzing ? 'Analyzing…' : 'Analyze saved capture' }}
        </button>
        <span class="muted small">
          {{
            capture.lastCapture
              ? `Target: ${capture.lastCapture.fileName}`
              : 'Capture and save a PNG before analyzing.'
          }}
        </span>
      </div>

      <p v-if="!capture.cropValid" class="muted small">
        The crop must stay inside the frame and be larger than zero.
      </p>

      <div v-if="capture.recognitionError" class="alert" role="alert">
        <strong>Recognition failed</strong>
        <span>{{ capture.recognitionError }}</span>
      </div>

      <div v-if="capture.lastRecognition" class="recognition-result">
        <dl class="details compact">
          <div>
            <dt>Set</dt>
            <dd>{{ capture.lastRecognition.setId }}</dd>
          </div>
          <div>
            <dt>Captured at</dt>
            <dd>{{ capture.lastRecognition.captureTimestamp }}</dd>
          </div>
          <div>
            <dt>OCR engine</dt>
            <dd>{{ recognitionMeta?.engine }}</dd>
          </div>
          <div>
            <dt>Elapsed</dt>
            <dd>{{ recognitionMeta?.elapsed }}</dd>
          </div>
          <div>
            <dt>Traits</dt>
            <dd>{{ capture.lastRecognition.traits.length }}</dd>
          </div>
          <div>
            <dt>Unknown rows</dt>
            <dd>{{ capture.lastRecognition.unknownRows.length }}</dd>
          </div>
        </dl>

        <table v-if="capture.lastRecognition.traits.length > 0" class="trait-table">
          <thead>
            <tr>
              <th scope="col">Trait</th>
              <th scope="col">Count</th>
              <th scope="col">Match</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="trait in capture.lastRecognition.traits" :key="trait.traitId">
              <td>
                <strong>{{ trait.displayName }}</strong>
                <small v-if="trait.rawText !== trait.displayName" class="muted">
                  {{ trait.rawText }}
                </small>
              </td>
              <td>{{ trait.count }}</td>
              <td class="muted small">
                {{ trait.match.method }} · {{ trait.match.score.toFixed(2) }}
              </td>
            </tr>
          </tbody>
        </table>

        <p v-else class="muted small">No trait rows were recognized in this crop.</p>

        <div v-if="capture.lastRecognition.unknownRows.length > 0" class="unknown-rows">
          <strong class="small">Unmatched rows</strong>
          <ul>
            <li v-for="(row, index) in capture.lastRecognition.unknownRows" :key="index">
              <code>{{ row.rawText || '(empty)' }}</code>
              <span v-if="row.count !== null"> × {{ row.count }}</span>
              <span class="muted small"> — {{ row.reason }}</span>
              <span v-if="row.candidateDisplayName" class="muted small">
                (closest: {{ row.candidateDisplayName }})
              </span>
            </li>
          </ul>
        </div>

        <details class="diagnostics-block">
          <summary>Diagnostics</summary>
          <pre class="diagnostics">{{ diagnosticsJson }}</pre>
        </details>
      </div>

      <p v-else class="muted small">
        Results include matched traits, unmatched rows, and diagnostics from the same versioned
        response the recognition CLI produces.
      </p>
    </article>

    <article class="panel">
      <div class="panel-heading">
        <div>
          <h2>Spike checklist</h2>
          <p class="muted">Record results in <code>docs/CAPTURE_SPIKE.md</code>.</p>
        </div>
      </div>
      <ol class="spike-list">
        <li>Capture the full TFT window and a full screen at 1080p.</li>
        <li>Repeat at 1440p or 4K, and at Windows display scaling 100%, 125%, 150%.</li>
        <li>Record the reported video frame size versus the display's physical size.</li>
        <li>Confirm the saved PNG matches the live preview and is not letterboxed.</li>
        <li>Note whether window capture includes the game boundary or overlays.</li>
        <li>Measure sustained frame rate over three seconds for the intended capture rate.</li>
      </ol>
    </article>
  </section>
</template>
