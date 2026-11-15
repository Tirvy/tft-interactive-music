import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { createInitialWorkerStatus, type WorkerStatus } from '@tft/shared-types/worker'
import { errorMessage } from '../utils/errors'

export const useWorkerStore = defineStore('worker', () => {
  const status = ref<WorkerStatus>(createInitialWorkerStatus())
  const logs = ref<string[]>([])
  const busy = ref(false)
  const error = ref<string | null>(null)

  let unsubscribe: (() => void) | null = null

  const isRunning = computed(() => status.value.state === 'running')
  const isBusy = computed(
    () => busy.value || status.value.state === 'starting' || status.value.state === 'stopping',
  )

  async function initialize(): Promise<void> {
    try {
      status.value = await window.tft.worker.getStatus()
      error.value = null
    } catch (cause) {
      error.value = errorMessage(cause)
    }

    if (!unsubscribe) {
      unsubscribe = window.tft.worker.onStatus((next) => {
        status.value = next
      })
    }
  }

  async function start(): Promise<void> {
    await run(() => window.tft.worker.start())
  }

  async function stop(): Promise<void> {
    await run(() => window.tft.worker.stop())
  }

  async function restart(): Promise<void> {
    await run(() => window.tft.worker.restart())
  }

  async function refreshLogs(): Promise<void> {
    try {
      logs.value = await window.tft.logs.tail(300)
    } catch (cause) {
      error.value = errorMessage(cause)
    }
  }

  async function revealLogs(): Promise<void> {
    try {
      await window.tft.logs.reveal()
    } catch (cause) {
      error.value = errorMessage(cause)
    }
  }

  function dispose(): void {
    unsubscribe?.()
    unsubscribe = null
  }

  async function run(action: () => Promise<WorkerStatus>): Promise<void> {
    busy.value = true
    error.value = null

    try {
      status.value = await action()
    } catch (cause) {
      error.value = errorMessage(cause)
    } finally {
      busy.value = false
    }
  }

  return {
    status,
    logs,
    busy,
    error,
    isRunning,
    isBusy,
    initialize,
    start,
    stop,
    restart,
    refreshLogs,
    revealLogs,
    dispose,
  }
})
