<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, type Component } from 'vue'
import type { AppView } from '@tft/shared-types/settings'
import StatusBadge from './components/StatusBadge.vue'
import CapturePage from './pages/CapturePage.vue'
import NowPlayingPage from './pages/NowPlayingPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import WorkerPage from './pages/WorkerPage.vue'
import { useCaptureStore } from './stores/capture'
import { useNavigationStore, useSettingsStore } from './stores/settings'
import { useWorkerStore } from './stores/worker'

const navigation = useNavigationStore()
const settings = useSettingsStore()
const worker = useWorkerStore()
const capture = useCaptureStore()

const navItems: Array<{ id: AppView; label: string; hint: string }> = [
  { id: 'now-playing', label: 'Now playing', hint: 'Status and active layers' },
  { id: 'capture', label: 'Capture', hint: 'Source selection and spike' },
  { id: 'worker', label: 'Worker', hint: 'Lifecycle and diagnostics' },
  { id: 'settings', label: 'Settings', hint: 'Paths and thresholds' },
]

const pages: Record<AppView, Component> = {
  'now-playing': NowPlayingPage,
  capture: CapturePage,
  worker: WorkerPage,
  settings: SettingsPage,
}

const currentPage = computed(() => pages[navigation.view])

onMounted(() => {
  void initialize()
})

onBeforeUnmount(() => {
  worker.dispose()
  capture.dispose()
})

async function initialize(): Promise<void> {
  await Promise.all([settings.load(), worker.initialize()])
  navigation.setView(settings.settings.ui.lastView)
}

function navigate(view: AppView): void {
  navigation.setView(view)

  if (settings.loaded) {
    void settings.update({ ui: { lastView: view } }).catch(() => undefined)
  }
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">TFT</div>
        <div>
          <strong>Soundtrack</strong>
          <small>Companion</small>
        </div>
      </div>

      <nav class="nav" aria-label="Main navigation">
        <button
          v-for="item in navItems"
          :key="item.id"
          type="button"
          class="nav-button"
          :class="{ active: navigation.view === item.id }"
          @click="navigate(item.id)"
        >
          <span>{{ item.label }}</span>
          <small>{{ item.hint }}</small>
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="sidebar-status">
          <span class="sidebar-label">Worker</span>
          <StatusBadge :state="worker.status.state" />
        </div>
        <div class="sidebar-status">
          <span class="sidebar-label">Capture source</span>
          <span class="sidebar-value">{{ capture.selectedSource?.name ?? 'Not selected' }}</span>
        </div>
        <p class="sidebar-note">Milestone 1 foundation. Recognition and audio are not wired yet.</p>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="topbar-title">
          <span class="eyebrow">Desktop foundation</span>
          <strong>{{ navItems.find((item) => item.id === navigation.view)?.label }}</strong>
        </div>
        <div class="topbar-status">
          <StatusBadge :state="worker.status.state" />
          <span class="muted">
            {{ capture.selectedSource?.name ?? 'No capture source selected' }}
          </span>
        </div>
      </header>

      <main class="content">
        <component :is="currentPage" />
      </main>
    </div>
  </div>
</template>
