<script setup lang="ts">
import { computed } from 'vue'
import type { WorkerState } from '@tft/shared-types/worker'

const props = defineProps<{ state: WorkerState }>()

const labels: Record<WorkerState, string> = {
  stopped: 'Worker stopped',
  starting: 'Worker starting',
  running: 'Worker running',
  stopping: 'Worker stopping',
  disconnected: 'Worker disconnected',
  error: 'Worker error',
}

const label = computed(() => labels[props.state])
</script>

<template>
  <span class="status-badge" :class="`state-${state}`">
    <span class="status-dot" />
    {{ label }}
  </span>
</template>
