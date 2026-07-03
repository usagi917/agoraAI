<script setup lang="ts">
const props = defineProps<{
  verdict: 'hit' | 'partial' | 'miss'
  jsd: number
  emd: number
  brier: number
}>()

const verdictLabels = {
  hit: '的中',
  partial: '部分的中',
  miss: '要改善',
}

function formatScore(value: number) {
  return value.toFixed(3)
}

function errorPoints(value: number) {
  return (value * 100).toFixed(1)
}
</script>

<template>
  <section class="verdict-card" :class="`verdict-${props.verdict}`">
    <div class="verdict-topline">
      <span class="verdict-badge">{{ verdictLabels[props.verdict] }}</span>
      <span class="verdict-error">誤差 {{ errorPoints(props.emd) }} pt</span>
    </div>
    <div class="score-grid">
      <div class="score-item">
        <span class="score-label">JSD</span>
        <strong>{{ formatScore(props.jsd) }}</strong>
      </div>
      <div class="score-item">
        <span class="score-label">EMD</span>
        <strong>{{ formatScore(props.emd) }}</strong>
      </div>
      <div class="score-item">
        <span class="score-label">Brier</span>
        <strong>{{ formatScore(props.brier) }}</strong>
      </div>
    </div>
  </section>
</template>

<style scoped>
.verdict-card {
  background: rgba(10, 10, 15, 0.82);
  border: 1px solid var(--border-active);
  border-radius: var(--radius);
  padding: 1rem;
  box-shadow: var(--shadow);
  backdrop-filter: blur(14px);
}

.verdict-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}

.verdict-badge {
  display: inline-flex;
  align-items: center;
  min-height: 1.75rem;
  padding: 0 0.7rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 700;
  background: var(--accent-subtle);
  color: var(--accent);
}

.verdict-hit .verdict-badge {
  background: rgba(34, 197, 94, 0.12);
  color: var(--success);
}

.verdict-partial .verdict-badge {
  background: rgba(245, 158, 11, 0.12);
  color: var(--warning);
}

.verdict-miss .verdict-badge {
  background: rgba(239, 68, 68, 0.12);
  color: var(--danger);
}

.verdict-error {
  color: var(--text-secondary);
  font-size: 0.82rem;
  white-space: nowrap;
}

.score-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
}

.score-item {
  min-width: 0;
  padding: 0.65rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
}

.score-label {
  display: block;
  color: var(--text-secondary);
  font-size: 0.68rem;
  margin-bottom: 0.15rem;
}

.score-item strong {
  font-family: var(--font-mono);
  font-size: 1rem;
  color: var(--text-primary);
}
</style>
