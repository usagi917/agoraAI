<script setup lang="ts">
import type { ColonyState } from '../stores/simulationStore'

defineProps<{
  colonies: ColonyState[]
}>()

const statusColor = (status: string) => {
  switch (status) {
    case 'completed': return 'var(--success)'
    case 'running': return 'var(--accent)'
    case 'failed': return 'var(--danger)'
    case 'queued': return 'var(--text-muted)'
    default: return 'var(--text-muted)'
  }
}

const statusLabel = (status: string) => {
  switch (status) {
    case 'completed': return '完了'
    case 'running': return '実行中'
    case 'failed': return '失敗'
    case 'queued': return '待機中'
    default: return status
  }
}

function progressPercent(colony: ColonyState): number {
  return colony.totalRounds > 0 ? (colony.currentRound / colony.totalRounds) * 100 : 0
}

function sparklinePoints(colony: ColonyState): string {
  if (colony.totalRounds <= 0) return ''
  const total = colony.totalRounds
  const current = colony.currentRound
  const width = 80
  const height = 16
  const points: string[] = []
  for (let i = 0; i <= Math.min(current, total); i++) {
    const x = (i / total) * width
    const y = height - (i / total) * height * 0.8 - Math.sin(i * 0.8) * 2
    points.push(`${x},${y}`)
  }
  return points.join(' ')
}
</script>

<template>
  <div class="colony-grid">
    <div
      v-for="colony in colonies"
      :key="colony.id"
      class="colony-card"
      :class="{ adversarial: colony.adversarial, running: colony.status === 'running', completed: colony.status === 'completed' }"
    >
      <!-- アクセントライン -->
      <div class="accent-line" :style="{ background: colony.status === 'running' ? `linear-gradient(90deg, var(--accent), var(--success))` : colony.status === 'completed' ? `var(--success)` : `var(--border)` }" />

      <div class="colony-header">
        <span class="colony-index">C{{ colony.colonyIndex + 1 }}</span>
        <span
          v-if="colony.adversarial"
          class="adversarial-badge"
          title="敵対的 Colony"
        >
          敵対
        </span>
        <span v-if="colony.status === 'completed'" class="check-badge">&#10003;</span>
      </div>

      <div class="colony-perspective">{{ colony.perspectiveLabel }}</div>

      <div class="colony-meta">
        <span class="meta-item" title="温度">T={{ colony.temperature }}</span>
        <span v-if="colony.eventCount" class="meta-item event-count" title="イベント数">{{ colony.eventCount }} events</span>
      </div>

      <!-- スパークライン -->
      <div v-if="colony.status === 'running' || colony.status === 'completed'" class="colony-sparkline">
        <svg viewBox="0 0 80 16" preserveAspectRatio="none" class="sparkline-svg">
          <polyline
            :points="sparklinePoints(colony)"
            fill="none"
            :stroke="colony.status === 'completed' ? 'var(--success)' : 'var(--accent)'"
            stroke-width="1.5"
            stroke-linejoin="round"
            stroke-linecap="round"
          />
        </svg>
      </div>

      <div class="colony-progress" v-if="colony.status === 'running'">
        <div class="progress-bar">
          <div
            class="progress-fill"
            :style="{ width: `${progressPercent(colony)}%` }"
          />
        </div>
        <span class="progress-text">{{ colony.currentRound }}/{{ colony.totalRounds }}</span>
      </div>

      <div class="colony-status">
        <span
          class="status-dot"
          :style="{ background: statusColor(colony.status) }"
        />
        {{ statusLabel(colony.status) }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.colony-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
  gap: 0.75rem;
}

.colony-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0;
  overflow: hidden;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.colony-card > *:not(.accent-line) {
  padding: 0 1rem;
}

.colony-card > .colony-header {
  padding-top: 0.75rem;
}

.colony-card > .colony-status {
  padding-bottom: 0.75rem;
}

.colony-card.running {
  border-color: var(--accent);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.08);
}

.colony-card.completed {
  border-color: rgba(34, 197, 94, 0.3);
}

.colony-card.adversarial {
  border-left: 3px solid var(--danger);
}

.accent-line {
  height: 3px;
  width: 100%;
}

.colony-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.colony-index {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text-primary);
}

.adversarial-badge {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--danger);
  background: rgba(239, 68, 68, 0.1);
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
}

.check-badge {
  font-size: 0.7rem;
  color: var(--success);
  font-weight: 700;
}

.colony-perspective {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
  line-height: 1.3;
}

.colony-meta {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.meta-item {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-muted);
}

.event-count {
  color: var(--accent);
  opacity: 0.7;
}

.colony-sparkline {
  height: 16px;
  margin-bottom: 0.4rem;
}

.sparkline-svg {
  width: 100%;
  height: 100%;
  opacity: 0.6;
}

.colony-progress {
  margin-bottom: 0.5rem;
}

.progress-bar {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 0.25rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--success));
  border-radius: 2px;
  transition: width 0.3s ease;
}

.progress-text {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--text-muted);
}

.colony-status {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.colony-card.running .status-dot {
  animation: pulse-dot 2s ease-in-out infinite;
}

@media (max-width: 640px) {
  .colony-grid {
    grid-template-columns: 1fr;
  }
}
</style>
