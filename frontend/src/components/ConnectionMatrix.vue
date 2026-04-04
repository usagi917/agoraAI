<script setup lang="ts">
import { computed } from 'vue'
import { useSocietyGraphStore } from '../stores/societyGraphStore'

const emit = defineEmits<{
  (e: 'highlight-edge', sourceId: string, targetId: string): void
}>()

const societyGraphStore = useSocietyGraphStore()

const agents = computed(() => {
  return Array.from(societyGraphStore.liveAgents.values()).map((a) => ({
    id: a.id,
    label: a.displayName || a.label,
    shortLabel: (a.displayName || a.label).slice(0, 4),
  }))
})

const matrix = computed(() => {
  const agentList = agents.value
  const rows: number[][] = []
  let maxVal = 1

  for (const rowAgent of agentList) {
    const row: number[] = []
    for (const colAgent of agentList) {
      if (rowAgent.id === colAgent.id) {
        row.push(-1)
      } else {
        const count = societyGraphStore.getInteractionCount(rowAgent.id, colAgent.id)
        if (count > maxVal) maxVal = count
        row.push(count)
      }
    }
    rows.push(row)
  }

  return { rows, maxVal }
})

function cellColor(value: number, maxVal: number): string {
  if (value < 0) return 'transparent'
  if (value === 0) return 'rgba(255, 255, 255, 0.03)'
  const intensity = Math.min(value / maxVal, 1)
  const alpha = 0.1 + intensity * 0.5
  return `rgba(0, 229, 255, ${alpha.toFixed(2)})`
}

function handleCellClick(rowIdx: number, colIdx: number) {
  const agentList = agents.value
  if (rowIdx === colIdx) return
  emit('highlight-edge', agentList[rowIdx].id, agentList[colIdx].id)
}
</script>

<template>
  <div class="conn-matrix">
    <div v-if="agents.length === 0" class="matrix-empty">
      エージェントデータを待機中...
    </div>
    <div v-else class="matrix-scroll">
      <div
        class="matrix-grid"
        :style="{
          gridTemplateColumns: `36px repeat(${agents.length}, minmax(32px, 1fr))`,
          minWidth: `${36 + agents.length * 38}px`,
        }"
      >
        <!-- Header -->
        <div class="matrix-corner"></div>
        <div
          v-for="agent in agents"
          :key="'h-' + agent.id"
          class="matrix-header"
          :title="agent.label"
        >{{ agent.shortLabel }}</div>

        <!-- Rows -->
        <template v-for="(row, i) in matrix.rows" :key="'r-' + i">
          <div class="matrix-row-label" :title="agents[i].label">{{ agents[i].shortLabel }}</div>
          <div
            v-for="(value, j) in row"
            :key="'c-' + j"
            class="matrix-cell"
            :class="{ clickable: i !== j && value > 0 }"
            :style="{ background: cellColor(value, matrix.maxVal) }"
            :title="i !== j ? `${agents[i].label} ↔ ${agents[j].label}: ${value}` : ''"
            @click="handleCellClick(i, j)"
          >
            <span v-if="i !== j && value > 0" class="cell-val">{{ value }}</span>
            <span v-else-if="i === j" class="cell-self">-</span>
          </div>
        </template>
      </div>
    </div>

    <div v-if="agents.length > 0" class="matrix-legend">
      <span class="legend-label">少</span>
      <div class="legend-bar"></div>
      <span class="legend-label">多</span>
    </div>
  </div>
</template>

<style scoped>
.conn-matrix {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.matrix-empty {
  text-align: center;
  color: var(--text-muted, rgba(150,150,170,0.5));
  font-size: 0.7rem;
  padding: 1rem;
}

.matrix-scroll {
  overflow-x: auto;
  padding-bottom: 0.2rem;
}

.matrix-grid {
  display: grid;
  gap: 2px;
}

.matrix-corner {}

.matrix-header {
  font-family: var(--font-mono, monospace);
  font-size: 0.6rem;
  font-weight: 600;
  color: var(--text-muted, rgba(150,150,170,0.5));
  text-align: center;
  padding: 0.2rem;
  overflow: hidden;
  text-overflow: ellipsis;
}

.matrix-row-label {
  font-family: var(--font-mono, monospace);
  font-size: 0.6rem;
  font-weight: 600;
  color: var(--text-muted, rgba(150,150,170,0.5));
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  text-overflow: ellipsis;
}

.matrix-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  min-height: 28px;
  transition: opacity 0.15s;
}
.matrix-cell.clickable {
  cursor: pointer;
}
.matrix-cell.clickable:hover {
  opacity: 0.75;
  outline: 1px solid rgba(0, 229, 255, 0.4);
}

.cell-val {
  font-family: var(--font-mono, monospace);
  font-size: 0.58rem;
  font-weight: 700;
  color: rgba(240, 240, 245, 0.9);
}

.cell-self {
  font-size: 0.55rem;
  color: var(--text-muted, rgba(150,150,170,0.3));
}

.matrix-legend {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  justify-content: center;
}

.legend-label {
  font-size: 0.6rem;
  color: var(--text-muted, rgba(150,150,170,0.5));
}

.legend-bar {
  width: 60px;
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(to right, rgba(255,255,255,0.03), rgba(0, 229, 255, 0.6));
}

.matrix-scroll::-webkit-scrollbar { height: 3px; }
.matrix-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
</style>
