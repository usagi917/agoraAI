<script setup lang="ts">
import { computed } from 'vue'
import { getStanceColor, STANCE_ORDER } from '../constants/stances'

const props = defineProps<{
  predicted: Record<string, number>
  actual: Record<string, number>
}>()

const rows = computed(() =>
  STANCE_ORDER.map((stance) => ({
    stance,
    color: getStanceColor(stance),
    predicted: props.predicted[stance] || 0,
    actual: props.actual[stance] || 0,
  })),
)

const predictedTotal = computed(() =>
  rows.value.reduce((sum, row) => sum + row.predicted, 0),
)
const actualTotal = computed(() =>
  rows.value.reduce((sum, row) => sum + row.actual, 0),
)

function pct(value: number) {
  return `${Math.round(value * 100)}%`
}
</script>

<template>
  <section class="distribution-compare">
    <div class="compare-header">
      <h2>分布比較</h2>
      <span>予測 {{ pct(predictedTotal) }} / 実測 {{ pct(actualTotal) }}</span>
    </div>
    <div class="compare-rows">
      <div v-for="row in rows" :key="row.stance" class="compare-row">
        <div class="stance-label">
          <span class="stance-swatch" :style="{ background: row.color }"></span>
          <span>{{ row.stance }}</span>
        </div>
        <div class="bar-pair">
          <div class="bar-track">
            <div
              class="bar-fill predicted"
              :style="{ width: pct(row.predicted), background: row.color }"
            ></div>
          </div>
          <div class="bar-track">
            <div
              class="bar-fill actual"
              :style="{ width: pct(row.actual), background: row.color }"
            ></div>
          </div>
        </div>
        <div class="values">
          <span>{{ pct(row.predicted) }}</span>
          <span>{{ pct(row.actual) }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.distribution-compare {
  background: rgba(10, 10, 15, 0.82);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
  backdrop-filter: blur(14px);
}

.compare-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}

.compare-header h2 {
  font-size: 0.95rem;
}

.compare-header span {
  color: var(--text-secondary);
  font-size: 0.72rem;
}

.compare-rows {
  display: grid;
  gap: 0.65rem;
}

.compare-row {
  display: grid;
  grid-template-columns: minmax(6rem, 8rem) 1fr auto;
  align-items: center;
  gap: 0.75rem;
}

.stance-label {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
  font-size: 0.78rem;
  color: var(--text-primary);
}

.stance-swatch {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  flex-shrink: 0;
}

.bar-pair {
  display: grid;
  gap: 0.25rem;
}

.bar-track {
  height: 0.42rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: inherit;
}

.bar-fill.predicted {
  opacity: 0.95;
}

.bar-fill.actual {
  opacity: 0.45;
}

.values {
  display: grid;
  grid-template-columns: 2.5rem 2.5rem;
  gap: 0.2rem;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-secondary);
  text-align: right;
}

@media (max-width: 640px) {
  .compare-row {
    grid-template-columns: 1fr;
    gap: 0.35rem;
  }

  .values {
    grid-template-columns: repeat(2, max-content);
    justify-content: end;
  }
}
</style>
