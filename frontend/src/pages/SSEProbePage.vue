<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

import { useSimulationStore } from '../stores/simulationStore'
import { useSimulationSSE } from '../composables/useSimulationSSE'

const store = useSimulationStore()
const sse = useSimulationSSE('probe-sim')

onMounted(() => {
  store.init('probe-sim', 'pipeline', 'probe')
  store.setStatus('running')
  sse.start()
})

onUnmounted(() => {
  sse.close()
})
</script>

<template>
  <main class="probe-page">
    <h2>SSE Probe</h2>
    <p data-testid="probe-status">status={{ store.status }}</p>
    <p data-testid="probe-phase">phase={{ store.phase }}</p>
    <p data-testid="probe-stage">stage={{ store.pipelineStage }}</p>
  </main>
</template>

<style scoped>
.probe-page {
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
