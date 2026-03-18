<script setup lang="ts">
import { computed } from 'vue'
import type { ColonyState } from '../stores/simulationStore'

const props = defineProps<{
  matrix: {
    colony_ids: string[]
    matrix: number[][]
  }
  colonies: ColonyState[]
}>()

const labels = computed(() => {
  return props.matrix.colony_ids.map((id, i) => {
    const colony = props.colonies.find(c => c.id === id)
    return colony ? `C${colony.colonyIndex + 1}` : `C${i + 1}`
  })
})

const cellColor = (value: number) => {
  if (value >= 0.8) return 'rgba(59, 130, 246, 0.6)'
  if (value >= 0.6) return 'rgba(59, 130, 246, 0.4)'
  if (value >= 0.4) return 'rgba(59, 130, 246, 0.25)'
  if (value >= 0.2) return 'rgba(59, 130, 246, 0.12)'
  return 'rgba(255, 255, 255, 0.03)'
}
</script>

<template>
  <div class="heatmap-container">
    <div class="heatmap-scroll">
      <div class="heatmap-grid" :style="{
        gridTemplateColumns: `40px repeat(${matrix.matrix.length}, minmax(36px, 1fr))`,
        minWidth: `${40 + matrix.matrix.length * 42}px`,
      }">
        <!-- Header row -->
        <div class="heatmap-corner"></div>
        <div
          v-for="(label, i) in labels"
          :key="'h-' + i"
          class="heatmap-header"
        >
          {{ label }}
        </div>

        <!-- Data rows -->
        <template v-for="(row, i) in matrix.matrix" :key="'r-' + i">
          <div class="heatmap-row-label">{{ labels[i] }}</div>
          <div
            v-for="(value, j) in row"
            :key="'c-' + j"
            class="heatmap-cell"
            :style="{ background: cellColor(value) }"
            :title="`${labels[i]} × ${labels[j]}: ${(value * 100).toFixed(0)}%`"
          >
            <span v-if="i !== j" class="cell-value">
              {{ (value * 100).toFixed(0) }}
            </span>
            <span v-else class="cell-value self">-</span>
          </div>
        </template>
      </div>
    </div>

    <div class="heatmap-legend">
      <span class="legend-label">低</span>
      <div class="legend-gradient"></div>
      <span class="legend-label">高</span>
    </div>
  </div>
</template>

<style scoped>
.heatmap-container {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.heatmap-scroll {
  overflow-x: auto;
  padding-bottom: 0.25rem;
}

.heatmap-grid {
  display: grid;
  gap: 2px;
}

.heatmap-corner {
  /* empty top-left corner */
}

.heatmap-header {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--text-muted);
  text-align: center;
  padding: 0.25rem;
}

.heatmap-row-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
}

.heatmap-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  min-height: 32px;
  cursor: default;
  transition: opacity 0.2s;
}

.heatmap-cell:hover {
  opacity: 0.8;
}

.cell-value {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: var(--text-primary);
  font-weight: 600;
}

.cell-value.self {
  color: var(--text-muted);
}

.heatmap-legend {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  justify-content: center;
}

.legend-label {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.legend-gradient {
  width: 100px;
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(
    to right,
    rgba(255, 255, 255, 0.03),
    rgba(59, 130, 246, 0.6)
  );
}

@media (max-width: 640px) {
  .heatmap-header,
  .heatmap-row-label {
    font-size: 0.62rem;
  }

  .heatmap-cell {
    min-height: 28px;
  }

  .cell-value {
    font-size: 0.56rem;
  }
}
</style>
