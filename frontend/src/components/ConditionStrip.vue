<script setup lang="ts">
import { computed } from 'vue'
import type { ValidationEvaluation } from '../api/client'

const props = defineProps<{
  evaluations: ValidationEvaluation[]
}>()

const sorted = computed(() =>
  [...props.evaluations].sort((a, b) => a.jsd - b.jsd),
)

function label(verdict: string) {
  if (verdict === 'hit') return 'Hit'
  if (verdict === 'partial') return 'Partial'
  return 'Miss'
}
</script>

<template>
  <section class="condition-strip">
    <article
      v-for="item in sorted"
      :key="item.survey_id"
      class="condition-card"
      :class="`condition-${item.verdict}`"
    >
      <div class="condition-label">{{ item.theme }}</div>
      <div class="condition-value">{{ item.jsd.toFixed(3) }}</div>
      <div class="condition-detail">{{ label(item.verdict) }} / EMD {{ item.emd.toFixed(3) }}</div>
    </article>
  </section>
</template>

<style scoped>
.condition-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  gap: 0.5rem;
}

.condition-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(10, 10, 15, 0.76);
  padding: 0.75rem;
  min-width: 0;
  backdrop-filter: blur(12px);
}

.condition-hit {
  border-color: rgba(34, 197, 94, 0.28);
}

.condition-partial {
  border-color: rgba(245, 158, 11, 0.28);
}

.condition-miss {
  border-color: rgba(239, 68, 68, 0.28);
}

.condition-label {
  color: var(--text-secondary);
  font-size: 0.72rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.condition-value {
  margin-top: 0.2rem;
  font-family: var(--font-mono);
  font-size: 1.1rem;
  color: var(--text-primary);
}

.condition-detail {
  color: var(--text-muted);
  font-size: 0.68rem;
}
</style>
