<script setup lang="ts">
import { computed } from 'vue'
import { useSimulationStore } from '../stores/simulationStore'

const store = useSimulationStore()

const phases = [
  { key: 'population', label: '人口生成', icon: '◈' },
  { key: 'selection', label: '選抜', icon: '◎' },
  { key: 'activation', label: '活性化', icon: '⬡' },
  { key: 'evaluation', label: '評価', icon: '▣' },
  { key: 'meeting', label: 'Meeting', icon: '◉' },
  { key: 'completed', label: '完了', icon: '✓' },
]

const phaseOrder = ['idle', 'population', 'selection', 'activation', 'evaluation', 'meeting', 'completed']

const currentPhaseIndex = computed(() => {
  const idx = phaseOrder.indexOf(store.societyPhase)
  return idx >= 0 ? idx : 0
})

function getPhaseStatus(phaseKey: string) {
  const target = phaseOrder.indexOf(phaseKey)
  const current = currentPhaseIndex.value
  if (target < current) return 'completed'
  if (target === current) return 'active'
  return 'pending'
}

const activationPercent = computed(() => {
  const { completed, total } = store.societyActivationProgress
  if (total <= 0) return 0
  return Math.round(completed / total * 100)
})
</script>

<template>
  <div class="society-progress">
    <div class="phase-timeline">
      <div
        v-for="phase in phases"
        :key="phase.key"
        class="phase-step"
        :class="getPhaseStatus(phase.key)"
      >
        <div class="phase-icon">{{ phase.icon }}</div>
        <div class="phase-label">{{ phase.label }}</div>
      </div>
    </div>

    <div v-if="store.societyPhase === 'activation' && store.societyActivationProgress.total > 0" class="activation-progress">
      <div class="progress-bar-track">
        <div class="progress-bar-fill" :style="{ width: activationPercent + '%' }" />
      </div>
      <span class="progress-text">
        {{ store.societyActivationProgress.completed }} / {{ store.societyActivationProgress.total }}
        ({{ activationPercent }}%)
      </span>
    </div>
  </div>
</template>

<style scoped>
.society-progress {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.phase-timeline {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.phase-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  flex: 1;
  opacity: 0.4;
  transition: opacity 0.3s;
}

.phase-step.active {
  opacity: 1;
}

.phase-step.completed {
  opacity: 0.8;
}

.phase-icon {
  font-size: 1.2rem;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
}

.phase-step.active .phase-icon {
  background: var(--accent-subtle);
  border-color: var(--accent);
  box-shadow: 0 0 8px var(--accent-glow);
}

.phase-step.completed .phase-icon {
  background: rgba(34, 197, 94, 0.15);
  border-color: var(--success);
}

.phase-label {
  font-size: 0.72rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
  text-align: center;
}

.phase-step.active .phase-label {
  color: var(--accent);
  font-weight: 600;
}

.activation-progress {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.progress-bar-track {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-text {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-muted);
  white-space: nowrap;
}
</style>
