<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  timesteps: Array<{
    timestep: number
    opinion_distribution: Record<string, number>
    cluster_count: number
  }>
}>()

const stanceColors: Record<string, string> = {
  '賛成': '#22c55e',
  '条件付き賛成': '#86efac',
  '中立': '#a3a3a3',
  '条件付き反対': '#fca5a5',
  '反対': '#ef4444',
}
const stanceOrder = ['賛成', '条件付き賛成', '中立', '条件付き反対', '反対']

const hasData = computed(() => props.timesteps.length >= 2)

// Stream/area chart dimensions
const width = 500
const height = 160
const pad = { top: 10, right: 10, bottom: 24, left: 10 }
const iw = width - pad.left - pad.right
const ih = height - pad.top - pad.bottom

// Build stacked stream paths
const streamPaths = computed(() => {
  if (!hasData.value) return []
  const ts = props.timesteps
  const n = ts.length
  const paths: Array<{ stance: string; color: string; d: string }> = []

  for (const stance of [...stanceOrder].reverse()) {
    const topPoints: string[] = []
    const bottomPoints: string[] = []

    for (let i = 0; i < n; i++) {
      const x = pad.left + (i / (n - 1)) * iw
      const dist = ts[i].opinion_distribution
      let cumBefore = 0
      let cumAfter = 0
      for (const s of stanceOrder) {
        const val = dist[s] || 0
        if (s === stance) {
          cumAfter = cumBefore + val
          break
        }
        cumBefore += val
      }
      const yTop = pad.top + (1 - cumAfter) * ih
      const yBottom = pad.top + (1 - cumBefore) * ih
      topPoints.push(`${x.toFixed(1)},${yTop.toFixed(1)}`)
      bottomPoints.unshift(`${x.toFixed(1)},${yBottom.toFixed(1)}`)
    }

    paths.push({
      stance,
      color: stanceColors[stance] || '#6366f1',
      d: `M ${topPoints.join(' L ')} L ${bottomPoints.join(' L ')} Z`,
    })
  }
  return paths
})

// Cluster count markers
const clusterMarkers = computed(() => {
  if (!hasData.value) return []
  const ts = props.timesteps
  const n = ts.length
  const markers: Array<{ x: number; count: number; timestep: number }> = []
  let prevCount = -1
  for (let i = 0; i < n; i++) {
    const count = ts[i].cluster_count
    if (count !== prevCount) {
      markers.push({
        x: pad.left + (i / (n - 1)) * iw,
        count,
        timestep: ts[i].timestep,
      })
      prevCount = count
    }
  }
  return markers
})

// X-axis labels
const xLabels = computed(() => {
  if (!hasData.value) return []
  const ts = props.timesteps
  const n = ts.length
  const step = Math.max(1, Math.floor(n / 5))
  return ts
    .filter((_: unknown, i: number) => i % step === 0 || i === n - 1)
    .map((t: { timestep: number }) => ({
      label: `t${t.timestep}`,
      x: pad.left + (t.timestep / Math.max(ts[n - 1].timestep, 1)) * iw,
    }))
})
</script>

<template>
  <div v-if="hasData" class="cluster-evolution-chart">
    <span class="chart-title">Cluster Evolution</span>
    <svg :viewBox="`0 0 ${width} ${height}`" class="stream-svg">
      <!-- Stream areas -->
      <path
        v-for="sp in streamPaths"
        :key="sp.stance"
        :d="sp.d"
        :fill="sp.color"
        fill-opacity="0.65"
        stroke="none"
      />

      <!-- Cluster count change markers -->
      <g v-for="marker in clusterMarkers" :key="'m' + marker.timestep">
        <line
          :x1="marker.x" :y1="pad.top"
          :x2="marker.x" :y2="pad.top + ih"
          stroke="rgba(255,255,255,0.15)"
          stroke-width="1"
          stroke-dasharray="3,3"
        />
        <circle
          :cx="marker.x" :cy="pad.top + 6"
          r="8"
          fill="rgba(99,102,241,0.3)"
          stroke="#818cf8"
          stroke-width="1"
        />
        <text
          :x="marker.x" :y="pad.top + 10"
          text-anchor="middle"
          fill="#c7d2fe"
          font-size="9"
          font-weight="bold"
        >{{ marker.count }}</text>
      </g>

      <!-- X-axis -->
      <text
        v-for="label in xLabels"
        :key="label.label"
        :x="label.x"
        :y="height - 4"
        text-anchor="middle"
        fill="rgba(255,255,255,0.35)"
        font-size="9"
      >{{ label.label }}</text>
    </svg>

    <!-- Legend -->
    <div class="stream-legend">
      <div v-for="stance in stanceOrder" :key="stance" class="legend-item">
        <span class="legend-dot" :style="{ backgroundColor: stanceColors[stance] }" />
        <span class="legend-text">{{ stance }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cluster-evolution-chart {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.chart-title {
  font-size: 0.72rem;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.4));
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.stream-svg {
  width: 100%;
  height: auto;
}

.stream-legend {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.legend-text {
  font-size: 0.68rem;
  color: var(--text-secondary);
}
</style>
