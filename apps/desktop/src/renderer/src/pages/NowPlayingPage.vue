<script setup lang="ts">
import { computed } from 'vue'
import type { AppView } from '@tft/shared-types/settings'
import { useCaptureStore } from '../stores/capture'
import { useNavigationStore } from '../stores/settings'
import { useWorkerStore } from '../stores/worker'

const navigation = useNavigationStore()
const worker = useWorkerStore()
const capture = useCaptureStore()

const recognitionReady = computed(() => false)
const audioReady = computed(() => false)

function go(view: AppView): void {
  navigation.setView(view)
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Now playing</h1>
        <p>
          Foundation status for the desktop app. Recognition and audio stay in their own packages
          and are not wired to the UI yet.
        </p>
      </div>
      <button type="button" class="button" @click="go('capture')">Open capture spike</button>
    </header>

    <div class="card-grid">
      <article class="panel card">
        <div class="card-heading">
          <span class="eyebrow">Recognition</span>
          <span class="pill" :class="{ ready: recognitionReady }">
            {{ recognitionReady ? 'Connected' : 'Not connected' }}
          </span>
        </div>
        <h2>Worker lifecycle</h2>
        <p class="muted">
          The Python worker is managed over stdio JSON lines. This milestone ships the lifecycle
          stub; OCR is added in Milestone 2.
        </p>
        <dl class="details compact">
          <div>
            <dt>State</dt>
            <dd>{{ worker.status.state }}</dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{{ worker.status.mode ?? '—' }}</dd>
          </div>
          <div>
            <dt>Last heartbeat</dt>
            <dd>{{ worker.status.lastHeartbeatAt ?? '—' }}</dd>
          </div>
        </dl>
        <button type="button" class="button subtle" @click="go('worker')">
          Worker diagnostics
        </button>
      </article>

      <article class="panel card">
        <div class="card-heading">
          <span class="eyebrow">Capture</span>
          <span class="pill" :class="{ ready: Boolean(capture.selectedSource) }">
            {{ capture.selectedSource ? 'Selected' : 'Not selected' }}
          </span>
        </div>
        <h2>{{ capture.selectedSource?.name ?? 'No source selected' }}</h2>
        <p class="muted">
          Select a screen or window, preview it, and save a full-resolution PNG for the capture
          spike.
        </p>
        <dl class="details compact">
          <div>
            <dt>Type</dt>
            <dd>{{ capture.selectedSource?.type ?? '—' }}</dd>
          </div>
          <div>
            <dt>Display</dt>
            <dd v-if="capture.selectedSource?.display">
              {{ capture.selectedSource.display.size.width }}×{{
                capture.selectedSource.display.size.height
              }}
              @ {{ capture.selectedSource.display.scaleFactor }}×
            </dd>
            <dd v-else>—</dd>
          </div>
        </dl>
        <button type="button" class="button subtle" @click="go('capture')">
          Select capture source
        </button>
      </article>

      <article class="panel card">
        <div class="card-heading">
          <span class="eyebrow">Music</span>
          <span class="pill">{{ audioReady ? 'Ready' : 'Planned' }}</span>
        </div>
        <h2>Layered playback</h2>
        <p class="muted">
          Web Audio stems, gain ramps, and next-bar transitions arrive in Milestone 5. No audio
          business logic lives in the renderer.
        </p>
        <dl class="details compact">
          <div>
            <dt>Active pack</dt>
            <dd>None</dd>
          </div>
          <div>
            <dt>Active layers</dt>
            <dd>0</dd>
          </div>
        </dl>
      </article>
    </div>

    <article class="panel">
      <div class="panel-heading">
        <div>
          <h2>Foundation scope</h2>
          <p class="muted">What is deliberately included in this slice.</p>
        </div>
        <button type="button" class="button subtle" @click="go('settings')">Settings</button>
      </div>
      <div class="checklist">
        <div>
          <strong>Workspace</strong>
          <span>pnpm workspace, shared contracts, lint, format, tests.</span>
        </div>
        <div>
          <strong>Desktop shell</strong>
          <span>Electron main, preload bridge, Vue 3 renderer, Pinia stores.</span>
        </div>
        <div>
          <strong>Worker lifecycle</strong>
          <span>Start, stop, restart, heartbeat timeout, disconnect status.</span>
        </div>
        <div>
          <strong>Capture spike</strong>
          <span>Source enumeration, live preview, PNG save, DPI diagnostics.</span>
        </div>
      </div>
      <p class="muted small">
        Selected set: no set catalog yet. Settings persist to the Electron userData directory.
      </p>
    </article>
  </section>
</template>
