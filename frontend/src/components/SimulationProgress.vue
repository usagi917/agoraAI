<script setup lang="ts">
import { computed } from 'vue'
import { useSimulationStore } from '../stores/simulationStore'

const store = useSimulationStore()

const singlePhases = [
  { key: 'world_building', label: 'モデル構築' },
  { key: 'simulation', label: 'シミュレーション' },
  { key: 'report', label: 'レポート生成' },
  { key: 'completed', label: '完了' },
]

const swarmPhases = [
  { key: 'world_building', label: '世界構築' },
  { key: 'colony_execution', label: 'Colony 実行' },
  { key: 'aggregation', label: '集約分析' },
  { key: 'completed', label: '完了' },
]

const pmBoardPhases = [
  { key: 'pm_analyzing', label: 'PM分析' },
  { key: 'pm_synthesizing', label: 'チーフPM統合' },
  { key: 'completed', label: '完了' },
]

const phases = computed(() => {
  if (store.mode === 'pm_board') return pmBoardPhases
  if (store.isSwarmMode) return swarmPhases
  return singlePhases
})

const currentPhaseIndex = computed(() => {
  const phase = store.phase
  const idx = phases.value.findIndex(p => p.key === phase || phase.startsWith(p.key))
  return idx >= 0 ? idx : 0
})

const progressPercent = computed(() => store.progress * 100)
</script>

<template>
  <div class="sim-progress">
    <div class="pipeline-segments">
      <div
        v-for="(p, i) in phases"
        :key="p.key"
        class="pipeline-segment"
        :class="{
          active: currentPhaseIndex === i,
          completed: currentPhaseIndex > i,
        }"
      >
        <span class="segment-label">{{ p.label }}</span>
      </div>
    </div>
    <div class="pipeline-track">
      <div class="pipeline-fill" :style="{ width: `${progressPercent}%` }"></div>
    </div>
    <div class="progress-meta">
      <span class="progress-status" :class="store.status">
        <span class="status-dot"></span>
        {{ store.status }}
      </span>
      <template v-if="!store.isSwarmMode">
        <span class="progress-info">Round {{ store.currentRound }}/{{ store.totalRounds || '?' }}</span>
      </template>
      <template v-else>
        <span class="progress-info">{{ store.completedColonies }}/{{ store.colonies.length }} Colony</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.sim-progress {
  padding: 1rem 1.5rem 0.75rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.pipeline-segments {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.pipeline-segment { flex: 1; text-align: center; }

.segment-label {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-muted);
  transition: color 0.3s;
}

.pipeline-segment.active .segment-label,
.pipeline-segment.completed .segment-label {
  color: var(--text-primary);
}

.pipeline-segment.active .segment-label { font-weight: 600; }

.pipeline-track {
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 0.6rem;
}

.pipeline-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--success), var(--accent));
  border-radius: 2px;
  transition: width 0.8s ease;
}

.progress-meta {
  display: flex;
  align-items: center;
  gap: 1rem;
  font-family: var(--font-mono);
  font-size: 0.72rem;
}

.progress-status {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  text-transform: uppercase;
  font-weight: 600;
  font-size: 0.68rem;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}

.progress-status.running .status-dot {
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent-glow);
  animation: pulse-dot 2s infinite;
}

.progress-status.completed .status-dot {
  background: var(--success);
  box-shadow: 0 0 6px var(--success-glow);
}

.progress-status.failed .status-dot { background: var(--danger); }

.progress-info { color: var(--text-muted); }
</style>
