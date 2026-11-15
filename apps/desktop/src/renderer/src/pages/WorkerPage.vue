<script setup lang="ts">
import { onMounted } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useWorkerStore } from '../stores/worker'

const worker = useWorkerStore()

onMounted(() => {
  void worker.initialize()
  void worker.refreshLogs()
})

function refresh(): void {
  void worker.refreshLogs()
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Worker lifecycle</h1>
        <p>
          The desktop process owns the Python worker. Messages are newline-delimited JSON over
          stdio; no local port is opened.
        </p>
      </div>
      <StatusBadge :state="worker.status.state" />
    </header>

    <div v-if="worker.error" class="alert" role="alert">
      <strong>Worker command failed</strong>
      <span>{{ worker.error }}</span>
    </div>

    <div v-if="worker.status.lastError" class="alert warning" role="status">
      <strong>{{ worker.status.lastError.code }}</strong>
      <span>{{ worker.status.lastError.message }}</span>
      <span v-if="worker.status.lastError.detail">{{ worker.status.lastError.detail }}</span>
    </div>

    <div class="worker-grid">
      <article class="panel">
        <div class="panel-heading">
          <div>
            <h2>Controls</h2>
            <p class="muted small">Start, stop, or restart the stub worker.</p>
          </div>
        </div>

        <div class="actions">
          <button
            type="button"
            class="button primary"
            :disabled="worker.isBusy || worker.status.state === 'running'"
            @click="worker.start()"
          >
            Start
          </button>
          <button
            type="button"
            class="button"
            :disabled="worker.isBusy || !worker.status.pid"
            @click="worker.stop()"
          >
            Stop
          </button>
          <button type="button" class="button" :disabled="worker.isBusy" @click="worker.restart()">
            Restart
          </button>
        </div>

        <dl class="details">
          <div>
            <dt>State</dt>
            <dd>{{ worker.status.state }}</dd>
          </div>
          <div>
            <dt>PID</dt>
            <dd>{{ worker.status.pid ?? '—' }}</dd>
          </div>
          <div>
            <dt>Worker version</dt>
            <dd>{{ worker.status.workerVersion ?? '—' }}</dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{{ worker.status.mode ?? '—' }}</dd>
          </div>
          <div class="span-2">
            <dt>Python executable</dt>
            <dd class="path">{{ worker.status.pythonPath ?? 'not resolved' }}</dd>
          </div>
          <div>
            <dt>Started at</dt>
            <dd>{{ worker.status.startedAt ?? '—' }}</dd>
          </div>
          <div>
            <dt>Ready at</dt>
            <dd>{{ worker.status.readyAt ?? '—' }}</dd>
          </div>
          <div>
            <dt>Last heartbeat</dt>
            <dd>{{ worker.status.lastHeartbeatAt ?? '—' }}</dd>
          </div>
          <div>
            <dt>Last pong</dt>
            <dd>{{ worker.status.lastPongAt ?? '—' }}</dd>
          </div>
          <div>
            <dt>Restart count</dt>
            <dd>{{ worker.status.restartCount }}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{{ worker.status.updatedAt }}</dd>
          </div>
        </dl>
      </article>

      <article class="panel">
        <div class="panel-heading">
          <div>
            <h2>Diagnostics</h2>
            <p class="muted small">The worker stub announces itself, heartbeats, and pings.</p>
          </div>
        </div>
        <ul class="plain-list">
          <li><strong>worker.ready</strong> includes a version and stub capabilities.</li>
          <li><strong>worker.heartbeat</strong> proves the process is alive.</li>
          <li><strong>worker.ping / pong</strong> checks the control channel.</li>
          <li><strong>worker.shutdown</strong> requests a graceful stop.</li>
          <li>Unexpected exit or a missed heartbeat becomes a visible disconnect.</li>
        </ul>
        <p class="muted small">
          OCR is intentionally absent from the worker in this milestone. The stub uses only the
          Python standard library so it starts quickly.
        </p>
      </article>
    </div>

    <article class="panel">
      <div class="panel-heading">
        <div>
          <h2>Recent log lines</h2>
          <p class="muted small">Local NDJSON log in the Electron userData directory.</p>
        </div>
        <div class="actions compact-actions">
          <button type="button" class="button subtle" @click="refresh">Refresh</button>
          <button type="button" class="button subtle" @click="worker.revealLogs()">
            Show log file
          </button>
        </div>
      </div>
      <pre class="logs">{{ worker.logs.join('\n') || 'No log lines yet.' }}</pre>
    </article>
  </section>
</template>
