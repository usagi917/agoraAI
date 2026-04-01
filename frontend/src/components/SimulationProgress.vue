<script setup lang="ts">
import { computed } from 'vue'
import { useSimulationStore } from '../stores/simulationStore'

const store = useSimulationStore()

const pipelinePhases = [
  { key: 'single', label: 'Stage 1: 因果推論' },
  { key: 'swarm', label: 'Stage 2: 多視点検証' },
  { key: 'pm_board', label: 'Stage 3: PM評価' },
  { key: 'completed', label: '完了' },
]

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

const unifiedPhases = [
  { key: 'society_pulse', label: '社会の脈動' },
  { key: 'council', label: '評議会' },
  { key: 'synthesis', label: '統合分析' },
]

const metaPhases = [
  { key: 'meta_world_building', label: '世界構築' },
  { key: 'meta_society', label: '社会反応' },
  { key: 'meta_issue_mining', label: '論点抽出' },
  { key: 'meta_issue_swarm', label: 'Issue Colony' },
  { key: 'meta_pm_board', label: 'PM介入' },
  { key: 'meta_scoring', label: '収束判定' },
  { key: 'completed', label: '完了' },
]

const phases = computed(() => {
  if (store.isUnifiedMode) return unifiedPhases
  if (store.isPipelineMode) return pipelinePhases
  if (store.isMetaMode) return metaPhases
  if (store.mode === 'pm_board') return pmBoardPhases
  if (store.mode === 'swarm' || store.mode === 'hybrid') return swarmPhases
  return singlePhases
})

const currentPhaseIndex = computed(() => {
  if (store.isUnifiedMode) {
    const idx = unifiedPhases.findIndex(p => p.key === store.unifiedPhase)
    return idx >= 0 ? idx : 0
  }
  if (store.isPipelineMode) {
    const idx = pipelinePhases.findIndex(p => p.key === store.pipelineStage)
    return idx >= 0 ? idx : 0
  }
  const phase = store.phase
  const idx = phases.value.findIndex(p => p.key === phase || phase.startsWith(p.key))
  return idx >= 0 ? idx : 0
})

const progressPercent = computed(() => store.progress * 100)

const progressInfo = computed(() => {
  if (store.status === 'generating_report' && store.reportSections.length > 0) {
    return `Report ${store.completedReportSections}/${store.reportSections.length}`
  }
  if (store.isUnifiedMode) {
    return `Phase ${store.unifiedPhaseIndex}/${store.unifiedPhaseTotal}`
  }
  if (store.isPipelineMode) {
    if (store.pipelineStage === 'single') {
      return `Round ${store.currentRound}/${store.totalRounds || '?'}`
    }
    if (store.pipelineStage === 'swarm' && store.colonies.length > 0) {
      return `${store.completedColonies}/${store.colonies.length} Colony`
    }
    if (store.pipelineStage === 'pm_board') {
      return 'PM分析中'
    }
    return ''
  }
  if (store.isMetaMode) {
    const score = store.metaBestScore > 0 ? `score ${(store.metaBestScore * 100).toFixed(0)}%` : ''
    return `Cycle ${store.metaCycleIndex}/${store.metaMaxCycles || '?'}${score ? ` · ${score}` : ''}`
  }
  if (store.mode === 'swarm' || store.mode === 'hybrid') {
    return `${store.completedColonies}/${store.colonies.length} Colony`
  }
  return `Round ${store.currentRound}/${store.totalRounds || '?'}`
})
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
          pending: currentPhaseIndex < i,
        }"
      >
        <div class="segment-indicator">
          <span v-if="currentPhaseIndex > i" class="check-icon">&#10003;</span>
          <span v-else-if="currentPhaseIndex === i" class="active-dot" />
          <span v-else class="pending-dot" />
        </div>
        <span class="segment-label">{{ p.label }}</span>
        <div v-if="currentPhaseIndex === i && progressInfo" class="segment-detail">
          {{ progressInfo }}
        </div>
      </div>
    </div>
    <div class="pipeline-track">
      <div class="pipeline-fill" :style="{ width: `${progressPercent}%` }" />
    </div>
    <div class="progress-meta">
      <span class="progress-status" :class="store.status">
        <span class="status-dot" />
        {{ store.status }}
      </span>
      <span v-if="progressInfo" class="progress-info">{{ progressInfo }}</span>
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
  gap: 0.25rem;
  margin-bottom: 0.6rem;
}

.pipeline-segment {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.4rem 0.25rem;
  border-radius: var(--radius-sm);
  transition: all 0.4s ease;
}

.pipeline-segment.active {
  flex: 2;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.pipeline-segment.completed {
  background: rgba(34, 197, 94, 0.06);
}

.pipeline-segment.pending {
  opacity: 0.5;
}

.segment-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
}

.check-icon {
  font-size: 0.7rem;
  color: var(--success);
  font-weight: 700;
}

.active-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent-glow);
  animation: pulse-dot 2s ease-in-out infinite;
}

.pending-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  opacity: 0.4;
}

.segment-label {
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--text-muted);
  text-align: center;
  transition: color 0.3s;
  line-height: 1.2;
}

.pipeline-segment.active .segment-label {
  color: var(--accent);
  font-weight: 700;
}

.pipeline-segment.completed .segment-label {
  color: var(--success);
  font-weight: 600;
}

.segment-detail {
  font-size: 0.62rem;
  font-family: var(--font-mono);
  color: var(--accent);
  opacity: 0.8;
  animation: fade-in 0.4s ease-out;
}

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

.progress-status.generating_report .status-dot,
.progress-status.running .status-dot,
.progress-status.connecting .status-dot {
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

@keyframes pulse-dot {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.25); opacity: 0.65; }
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 0.8; transform: translateY(0); }
}
</style>
