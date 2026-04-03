<script setup lang="ts">
import { computed } from 'vue'
import { useTheaterStore } from '../stores/theaterStore'

const theater = useTheaterStore()

const stanceColor: Record<string, string> = {
  '賛成': 'var(--success)',
  '条件付き賛成': '#86efac',
  '中立': 'var(--text-muted)',
  '条件付き反対': '#fca5a5',
  '反対': 'var(--danger)',
}

function getStanceColor(stance: string): string {
  return stanceColor[stance] ?? 'var(--text-secondary)'
}

const topClaim = computed(() => theater.latestClaim)
const topShift = computed(() => theater.latestShift)
const topAlliance = computed(() => theater.latestAlliance)
const decisionResult = computed(() => theater.decision)

const hasContent = computed(() =>
  topClaim.value || topShift.value || topAlliance.value || decisionResult.value,
)
</script>

<template>
  <div class="debate-cards">
    <h4 class="debate-cards-title">議論ライブ</h4>

    <div v-if="!hasContent" class="debate-placeholder">
      <span class="debate-placeholder-icon">◌</span>
      <span class="debate-placeholder-text">議論開始を待機中</span>
    </div>

    <template v-else>
      <!-- Decision (top priority when available) -->
      <div v-if="decisionResult" class="debate-card decision-card">
        <div class="card-label">結論</div>
        <p class="card-body decision-text">{{ decisionResult.decisionText }}</p>
        <div class="card-meta">
          <span class="confidence-badge">信頼度 {{ Math.round(decisionResult.confidence * 100) }}%</span>
          <span v-if="decisionResult.dissentCount > 0" class="dissent-badge">反対 {{ decisionResult.dissentCount }}人</span>
        </div>
      </div>

      <!-- Latest Claim -->
      <div v-if="topClaim" class="debate-card claim-card">
        <div class="card-label">最新の主張</div>
        <p class="card-body">{{ topClaim.claimText }}</p>
        <div class="card-meta">
          <span class="agent-tag">{{ topClaim.agentId }}</span>
          <span class="stance-tag" :style="{ color: getStanceColor(topClaim.stance) }">{{ topClaim.stance }}</span>
        </div>
      </div>

      <!-- Latest Stance Shift -->
      <div v-if="topShift" class="debate-card shift-card">
        <div class="card-label">立場変化</div>
        <p class="card-body shift-body">
          <span class="shift-from" :style="{ color: getStanceColor(topShift.fromStance) }">{{ topShift.fromStance }}</span>
          <span class="shift-arrow">→</span>
          <span class="shift-to" :style="{ color: getStanceColor(topShift.toStance) }">{{ topShift.toStance }}</span>
        </p>
        <div class="card-meta">
          <span class="agent-tag">{{ topShift.agentId }}</span>
        </div>
      </div>

      <!-- Latest Alliance -->
      <div v-if="topAlliance" class="debate-card alliance-card">
        <div class="card-label">連合</div>
        <p class="card-body">{{ topAlliance.agentIds.length }}人が「{{ topAlliance.stance }}」で一致</p>
        <div class="card-meta">
          <span class="alliance-members">{{ topAlliance.agentIds.slice(0, 3).join(', ') }}{{ topAlliance.agentIds.length > 3 ? ` +${topAlliance.agentIds.length - 3}人` : '' }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.debate-cards {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.debate-cards-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.debate-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  color: var(--text-muted);
}

.debate-placeholder-icon {
  font-size: var(--text-2xl);
  animation: breathe 3s ease-in-out infinite;
}

.debate-placeholder-text {
  font-size: var(--text-sm);
}

.debate-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-3);
  animation: slide-in-right 0.3s ease-out;
}

.card-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: var(--space-1);
}

.card-body {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.5;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
  font-size: var(--text-xs);
}

.agent-tag {
  font-family: var(--font-mono);
  color: var(--accent);
}

.stance-tag {
  font-weight: 600;
}

.shift-body {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
}

.shift-arrow {
  color: var(--text-muted);
}

.decision-card {
  border-color: var(--accent);
  background: rgba(59, 130, 246, 0.06);
}

.decision-text {
  font-size: var(--text-base);
  font-weight: 600;
}

.confidence-badge {
  font-family: var(--font-mono);
  color: var(--success);
  font-weight: 600;
}

.dissent-badge {
  font-family: var(--font-mono);
  color: var(--warning);
}

.alliance-members {
  font-family: var(--font-mono);
  color: var(--text-secondary);
}
</style>
