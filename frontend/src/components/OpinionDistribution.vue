<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  distribution: Record<string, number>
}>()

const stanceColors: Record<string, string> = {
  '賛成': '#22c55e',
  '反対': '#ef4444',
  '中立': '#a3a3a3',
  '条件付き賛成': '#86efac',
  '条件付き反対': '#fca5a5',
}

const sortedEntries = computed(() => {
  const order = ['賛成', '条件付き賛成', '中立', '条件付き反対', '反対']
  return Object.entries(props.distribution).sort((a, b) => {
    const ia = order.indexOf(a[0])
    const ib = order.indexOf(b[0])
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })
})
</script>

<template>
  <div class="opinion-distribution">
    <div class="bar-container">
      <div
        v-for="[stance, ratio] in sortedEntries"
        :key="stance"
        class="bar-segment"
        :style="{
          width: (ratio * 100) + '%',
          backgroundColor: stanceColors[stance] || '#6366f1',
        }"
        :title="`${stance}: ${(ratio * 100).toFixed(1)}%`"
      />
    </div>
    <div class="legend">
      <div v-for="[stance, ratio] in sortedEntries" :key="stance" class="legend-item">
        <span class="legend-dot" :style="{ backgroundColor: stanceColors[stance] || '#6366f1' }" />
        <span class="legend-label">{{ stance }}</span>
        <span class="legend-value">{{ (ratio * 100).toFixed(1) }}%</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.opinion-distribution {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.bar-container {
  display: flex;
  height: 32px;
  border-radius: var(--radius-sm, 4px);
  overflow: hidden;
  background: rgba(255, 255, 255, 0.05);
}

.bar-segment {
  transition: width 0.6s ease;
  min-width: 2px;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  color: var(--text-secondary);
}

.legend-value {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-primary);
}
</style>
