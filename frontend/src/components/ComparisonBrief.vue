<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ComparisonResult } from '../stores/scenarioPairStore'
import type { DecisionBrief as DecisionBriefType } from '../api/client'
import DecisionBrief from './DecisionBrief.vue'

const props = defineProps<{
  comparison: ComparisonResult
}>()

const activeTab = ref<'baseline' | 'intervention'>('baseline')

function toDecisionBrief(value: unknown): DecisionBriefType | null {
  if (!value || typeof value !== 'object') return null

  const recommendation = (value as { recommendation?: unknown }).recommendation
  if (
    recommendation !== 'Go'
    && recommendation !== 'No-Go'
    && recommendation !== '条件付きGo'
  ) {
    return null
  }

  return value as DecisionBriefType
}

const baselineBrief = computed<DecisionBriefType | null>(() =>
  toDecisionBrief(props.comparison.baseline_brief),
)
const interventionBrief = computed<DecisionBriefType | null>(() =>
  toDecisionBrief(props.comparison.intervention_brief),
)
const delta = computed(() => props.comparison.delta)

function formatChange(value: number): string {
  const pct = (value * 100).toFixed(1)
  return value >= 0 ? `+${pct}%` : `${pct}%`
}
</script>

<template>
  <div class="comparison-brief" data-testid="comparison-brief">
    <!-- Desktop: two-column grid -->
    <div class="comparison-grid">
      <div class="comparison-column" data-testid="baseline-panel">
        <div class="column-header">
          <span class="column-badge column-badge-baseline">介入なし</span>
        </div>
        <div v-if="baselineBrief" class="card column-body">
          <DecisionBrief :brief="baselineBrief" />
        </div>
        <div v-else class="card column-body column-empty">
          <p class="empty-text">介入なしのデータはまだありません</p>
        </div>
      </div>
      <div class="comparison-column" data-testid="intervention-panel">
        <div class="column-header">
          <span class="column-badge column-badge-intervention">介入あり</span>
        </div>
        <div v-if="interventionBrief" class="card column-body">
          <DecisionBrief :brief="interventionBrief" />
        </div>
        <div v-else class="card column-body column-empty">
          <p class="empty-text">介入ありのデータはまだありません</p>
        </div>
      </div>
    </div>

    <!-- Mobile: tabs -->
    <div class="comparison-tabs">
      <button
        class="tab-btn"
        :class="{ 'tab-btn-active': activeTab === 'baseline' }"
        @click="activeTab = 'baseline'"
      >
        介入なし
      </button>
      <button
        class="tab-btn"
        :class="{ 'tab-btn-active': activeTab === 'intervention' }"
        @click="activeTab = 'intervention'"
      >
        介入あり
      </button>
    </div>
    <div class="comparison-tab-content">
      <div v-if="activeTab === 'baseline'" class="card">
        <DecisionBrief v-if="baselineBrief" :brief="baselineBrief" />
        <p v-else class="empty-text">介入なしのデータはまだありません</p>
      </div>
      <div v-if="activeTab === 'intervention'" class="card">
        <DecisionBrief v-if="interventionBrief" :brief="interventionBrief" />
        <p v-else class="empty-text">介入ありのデータはまだありません</p>
      </div>
    </div>

    <!-- Delta summary -->
    <div class="delta-summary card" data-testid="delta-summary">
      <h3 class="delta-title">違いの要約</h3>
      <div class="delta-grid">
        <div class="delta-metric">
          <span class="delta-label">支持の変化</span>
          <span
            class="delta-value"
            :class="delta.support_change >= 0 ? 'delta-positive' : 'delta-negative'"
          >
            {{ formatChange(delta.support_change) }}
          </span>
        </div>
        <div v-if="delta.new_concerns.length" class="delta-section">
          <span class="delta-label">新しく増えた懸念</span>
          <ul class="delta-list">
            <li v-for="(concern, i) in delta.new_concerns" :key="i">{{ concern }}</li>
          </ul>
        </div>
        <div v-if="delta.key_differences.length" class="delta-section">
          <span class="delta-label">主な違い</span>
          <ul class="delta-list">
            <li v-for="(diff, i) in delta.key_differences" :key="i">{{ diff }}</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.comparison-brief {
  display: flex;
  flex-direction: column;
  gap: var(--section-gap);
}

.comparison-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--section-gap);
}

.comparison-column {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.column-header {
  display: flex;
  align-items: center;
}

.column-badge {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  font-weight: 600;
  padding: var(--space-1) var(--space-3);
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.column-badge-baseline {
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.column-badge-intervention {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.column-body {
  flex: 1;
}

.column-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
}

.empty-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

/* Mobile tabs - hidden on desktop */
.comparison-tabs {
  display: none;
  gap: var(--space-2);
}

.comparison-tab-content {
  display: none;
}

.tab-btn {
  flex: 1;
  padding: var(--space-2) var(--space-4);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-btn-active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

/* Delta summary */
.delta-summary {
  animation: fade-in 0.4s ease-out;
}

.delta-title {
  font-size: var(--text-lg);
  font-weight: 700;
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}

.delta-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.delta-metric {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.delta-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
}

.delta-value {
  font-family: var(--font-mono);
  font-size: var(--text-xl);
  font-weight: 700;
}

.delta-positive {
  color: var(--success);
}

.delta-negative {
  color: var(--danger);
}

.delta-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.delta-list {
  padding-left: var(--space-6);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.8;
}

@media (max-width: 640px) {
  .comparison-grid {
    display: none;
  }

  .comparison-tabs {
    display: flex;
  }

  .comparison-tab-content {
    display: block;
  }
}

@media print {
  .comparison-tabs,
  .comparison-tab-content {
    display: none !important;
  }
  .comparison-grid {
    display: grid !important;
  }
  .delta-summary {
    break-inside: avoid;
  }
}
</style>
