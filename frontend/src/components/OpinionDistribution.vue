<script setup lang="ts">
import { computed } from 'vue'
import { getStanceColor, getStanceSortIndex } from '../constants/stances'

const props = defineProps<{
  distribution: Record<string, number>
}>()

const sortedEntries = computed(() => {
  return Object.entries(props.distribution).sort((a, b) => {
    return getStanceSortIndex(a[0]) - getStanceSortIndex(b[0])
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
          backgroundColor: getStanceColor(stance),
        }"
        :title="`${stance}: ${(ratio * 100).toFixed(1)}%`"
      />
    </div>
    <div class="legend">
      <div v-for="[stance, ratio] in sortedEntries" :key="stance" class="legend-item">
        <span class="legend-dot" :style="{ backgroundColor: getStanceColor(stance) }" />
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
