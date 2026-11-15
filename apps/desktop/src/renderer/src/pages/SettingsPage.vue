<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import type { AppInfo } from '@tft/shared-types/ipc'
import { useSettingsStore } from '../stores/settings'
import { errorMessage } from '../utils/errors'

const settings = useSettingsStore()

const form = reactive({
  pythonPath: '',
  autoStart: true,
  startupTimeoutMs: 20_000,
  heartbeatIntervalMs: 5000,
  heartbeatTimeoutMs: 14_000,
  frameRate: 4,
  saveDirectory: '',
})

const saving = ref(false)
const message = ref<string | null>(null)
const appInfo = ref<AppInfo | null>(null)

watch(
  () => settings.settings,
  (next) => {
    form.pythonPath = next.worker.pythonPath ?? ''
    form.autoStart = next.worker.autoStart
    form.startupTimeoutMs = next.worker.startupTimeoutMs
    form.heartbeatIntervalMs = next.worker.heartbeatIntervalMs
    form.heartbeatTimeoutMs = next.worker.heartbeatTimeoutMs
    form.frameRate = next.capture.frameRate
    form.saveDirectory = next.capture.saveDirectory ?? ''
  },
  { immediate: true, deep: true },
)

onMounted(() => {
  void loadAppInfo()
})

async function loadAppInfo(): Promise<void> {
  try {
    appInfo.value = await window.tft.app.getInfo()
  } catch (cause) {
    message.value = errorMessage(cause)
  }
}

async function save(): Promise<void> {
  saving.value = true
  message.value = null

  try {
    await settings.update({
      capture: {
        frameRate: Number(form.frameRate),
        saveDirectory: form.saveDirectory.trim() || null,
      },
      worker: {
        pythonPath: form.pythonPath.trim() || null,
        autoStart: form.autoStart,
        startupTimeoutMs: Number(form.startupTimeoutMs),
        heartbeatIntervalMs: Number(form.heartbeatIntervalMs),
        heartbeatTimeoutMs: Number(form.heartbeatTimeoutMs),
      },
    })
    message.value =
      'Settings saved. Restart the worker if the Python path or heartbeat thresholds changed.'
  } catch {
    // The settings store exposes the validation error.
  } finally {
    saving.value = false
  }
}

function openUserData(): void {
  void window.tft.app.openUserData()
}

function revealLogs(): void {
  void window.tft.logs.reveal()
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Settings</h1>
        <p>
          App settings are stored as validated JSON in the Electron userData directory. These values
          control the worker process and capture spike defaults.
        </p>
      </div>
      <button type="button" class="button primary" :disabled="saving" @click="save">
        {{ saving ? 'Saving…' : 'Save settings' }}
      </button>
    </header>

    <div v-if="settings.error" class="alert" role="alert">
      <strong>Settings error</strong>
      <span>{{ settings.error }}</span>
    </div>

    <div v-if="message" class="alert success" role="status">
      <span>{{ message }}</span>
    </div>

    <div class="settings-grid">
      <article class="panel">
        <div class="panel-heading">
          <div>
            <h2>Recognition worker</h2>
            <p class="muted small">Leave the Python path empty to probe project venvs.</p>
          </div>
        </div>

        <form class="form-grid" @submit.prevent="save">
          <label class="span-2">
            <span>Python executable</span>
            <input
              v-model="form.pythonPath"
              type="text"
              placeholder="C:\path\to\python.exe"
              spellcheck="false"
            />
          </label>

          <label class="checkbox span-2">
            <input v-model="form.autoStart" type="checkbox" />
            <span>Start the worker when the app launches</span>
          </label>

          <label>
            <span>Startup timeout (ms)</span>
            <input v-model.number="form.startupTimeoutMs" type="number" min="3000" max="120000" />
          </label>

          <label>
            <span>Heartbeat interval (ms)</span>
            <input v-model.number="form.heartbeatIntervalMs" type="number" min="500" max="30000" />
          </label>

          <label>
            <span>Heartbeat timeout (ms)</span>
            <input v-model.number="form.heartbeatTimeoutMs" type="number" min="1000" max="120000" />
          </label>

          <p class="muted small span-2">
            The timeout must be greater than the interval. A missed heartbeat marks the worker
            disconnected and terminates the child process.
          </p>
        </form>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <h2>Capture spike</h2>
            <p class="muted small">Defaults used by the capture page.</p>
          </div>
        </div>

        <form class="form-grid" @submit.prevent="save">
          <label>
            <span>Preferred frame rate</span>
            <input v-model.number="form.frameRate" type="number" min="1" max="30" />
          </label>

          <label class="span-2">
            <span>Capture directory</span>
            <input
              v-model="form.saveDirectory"
              type="text"
              placeholder="Default: <userData>/captures"
              spellcheck="false"
            />
          </label>

          <p class="muted small span-2">
            The requested frame rate is a constraint hint. The capture page measures the delivered
            rate so the spike records what Windows actually provides.
          </p>
        </form>
      </article>

      <article class="panel span-full">
        <div class="panel-heading">
          <div>
            <h2>Paths</h2>
            <p class="muted small">Local-only application data.</p>
          </div>
          <div class="actions compact-actions">
            <button type="button" class="button subtle" @click="openUserData">Open userData</button>
            <button type="button" class="button subtle" @click="revealLogs">Show log file</button>
          </div>
        </div>

        <dl v-if="appInfo" class="details">
          <div>
            <dt>App version</dt>
            <dd>{{ appInfo.version }}</dd>
          </div>
          <div>
            <dt>Electron</dt>
            <dd>{{ appInfo.electron }}</dd>
          </div>
          <div>
            <dt>Chromium</dt>
            <dd>{{ appInfo.chrome }}</dd>
          </div>
          <div>
            <dt>Node</dt>
            <dd>{{ appInfo.node }}</dd>
          </div>
          <div class="span-2">
            <dt>userData</dt>
            <dd class="path">{{ appInfo.userDataPath }}</dd>
          </div>
          <div class="span-2">
            <dt>Captures</dt>
            <dd class="path">{{ appInfo.capturesPath }}</dd>
          </div>
          <div class="span-2">
            <dt>Log file</dt>
            <dd class="path">{{ appInfo.logsPath }}</dd>
          </div>
          <div class="span-2">
            <dt>Recognition project</dt>
            <dd class="path">{{ appInfo.recognitionDir ?? 'not found' }}</dd>
          </div>
        </dl>
        <p v-else class="muted small">Loading application paths…</p>
      </article>
    </div>
  </section>
</template>
