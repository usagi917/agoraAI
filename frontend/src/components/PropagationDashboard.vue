<script setup lang="ts">
import { computed } from 'vue'
import { useSimulationStore } from '../stores/simulationStore'
import ClusterEvolutionChart from './ClusterEvolutionChart.vue'

/**
 * Props for hydration from API (completed simulations).
 * Falls back to store (SSE real-time) when not provided.
 */
const props = withDefaults(defineProps<{
  apiData?: {
    converged?: boolean
    total_timesteps?: number
    cluster_count?: number
    clusters?: Array<{ label: number; size: number; centroid: number[] }>
    echo_chamber?: { homophily_index: number; polarization_index: number }
    stigmergy_topics?: Array<{ topic: string; intensity: number }>
    prediction_market?: Record<string, number>
    phase_transitions?: Array<{ timestep: number; type: string }>
    tipping_points?: Array<{ timestep: number; cascade_ratio: number }>
  } | null
}>(), {
  apiData: null,
})

const store = useSimulationStore()

const stanceColors: Record<string, string> = {
  '賛成': '#22c55e',
  '反対': '#ef4444',
  '中立': '#a3a3a3',
  '条件付き賛成': '#86efac',
  '条件付き反対': '#fca5a5',
}

const stanceOrder = ['賛成', '条件付き賛成', '中立', '条件付き反対', '反対']

// Use SSE store data (live) OR props from API (completed)
const timesteps = computed(() => store.propagationTimesteps)
const hasStoreData = computed(() => timesteps.value.length > 0)
const hasApiData = computed(() => !!props.apiData && (props.apiData.cluster_count ?? 0) > 0)
const hasData = computed(() => hasStoreData.value || hasApiData.value)

// Derived: clusters from API or store
const clusters = computed(() => {
  if (hasApiData.value && props.apiData?.clusters) return props.apiData.clusters
  return store.propagationClusters
})

const echoMetrics = computed(() => {
  if (hasApiData.value && props.apiData?.echo_chamber) return props.apiData.echo_chamber
  return store.echoChamberMetrics
})

const isConverged = computed(() => {
  if (hasApiData.value) return props.apiData?.converged ?? false
  return store.propagationCompleted
})

const totalTimesteps = computed(() => {
  if (hasApiData.value) return props.apiData?.total_timesteps ?? 0
  return timesteps.value.length
})

const clusterCount = computed(() => {
  if (hasApiData.value) return props.apiData?.cluster_count ?? 0
  return finalClusterCount.value
})

const stigmergyTopics = computed(() => {
  if (hasApiData.value) return props.apiData?.stigmergy_topics ?? []
  return []
})

const predictionMarket = computed(() => {
  if (hasApiData.value) return props.apiData?.prediction_market ?? {}
  return {}
})

const phaseTransitions = computed(() => {
  if (hasApiData.value) return props.apiData?.phase_transitions ?? []
  return []
})

const tippingPoints = computed(() => {
  if (hasApiData.value) return props.apiData?.tipping_points ?? []
  return []
})

// SVG dimensions
const chartWidth = 600
const chartHeight = 200
const padding = { top: 20, right: 20, bottom: 30, left: 40 }
const innerWidth = chartWidth - padding.left - padding.right
const innerHeight = chartHeight - padding.top - padding.bottom

// Time series area chart data (stacked)
const stackedAreas = computed(() => {
  if (!hasData.value) return []

  const ts = timesteps.value
  const areas: Array<{ stance: string; color: string; points: string }> = []

  for (const stance of [...stanceOrder].reverse()) {
    const points: string[] = []
    const bottomPoints: string[] = []

    for (let i = 0; i < ts.length; i++) {
      const x = padding.left + (i / Math.max(ts.length - 1, 1)) * innerWidth
      const dist = ts[i].opinion_distribution

      // Compute cumulative Y for stacking
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

      const yTop = padding.top + (1 - cumAfter) * innerHeight
      const yBottom = padding.top + (1 - cumBefore) * innerHeight

      points.push(`${x},${yTop}`)
      bottomPoints.unshift(`${x},${yBottom}`)
    }

    areas.push({
      stance,
      color: stanceColors[stance] || '#6366f1',
      points: [...points, ...bottomPoints].join(' '),
    })
  }

  return areas
})

// Delta sparkline
const deltaPath = computed(() => {
  if (timesteps.value.length < 2) return ''
  const ts = timesteps.value
  const maxDelta = Math.max(...ts.map((t: { max_delta: number }) => t.max_delta), 0.01)
  const points = ts.map((t: { max_delta: number }, i: number) => {
    const x = padding.left + (i / (ts.length - 1)) * innerWidth
    const y = padding.top + (1 - t.max_delta / maxDelta) * innerHeight
    return `${x},${y}`
  })
  return `M ${points.join(' L ')}`
})

// X-axis labels
const xLabels = computed(() => {
  if (timesteps.value.length === 0) return []
  const ts = timesteps.value
  const step = Math.max(1, Math.floor(ts.length / 5))
  return ts
    .filter((_: unknown, i: number) => i % step === 0 || i === ts.length - 1)
    .map((t: { timestep: number }) => ({
      label: `t${t.timestep}`,
      x: padding.left + (t.timestep / Math.max(ts[ts.length - 1].timestep, 1)) * innerWidth,
    }))
})

// Cluster count
const finalClusterCount = computed(() => {
  if (timesteps.value.length === 0) return 0
  return timesteps.value[timesteps.value.length - 1].cluster_count
})

// Last values
const lastEntropy = computed(() => {
  if (timesteps.value.length === 0) return 0
  return timesteps.value[timesteps.value.length - 1].entropy
})

</script>

<template>
  <div v-if="hasData" class="propagation-dashboard">
    <h4 class="dashboard-title">Network Propagation</h4>

    <!-- Metrics row -->
    <div class="metrics-row">
      <div class="metric-card">
        <span class="metric-label">Timesteps</span>
        <span class="metric-value">{{ totalTimesteps }}</span>
      </div>
      <div class="metric-card">
        <span class="metric-label">Clusters</span>
        <span class="metric-value">{{ clusterCount }}</span>
      </div>
      <div v-if="hasStoreData" class="metric-card">
        <span class="metric-label">Entropy</span>
        <span class="metric-value">{{ lastEntropy.toFixed(2) }}</span>
      </div>
      <div class="metric-card">
        <span class="metric-label">Convergence</span>
        <span class="metric-value" :class="{ converged: isConverged }">
          {{ isConverged ? 'Yes' : 'Running' }}
        </span>
      </div>
      <div v-if="echoMetrics.homophily_index > 0" class="metric-card">
        <span class="metric-label">Echo Chamber</span>
        <span class="metric-value" :class="{ warning: echoMetrics.homophily_index > 0.6 }">
          {{ (echoMetrics.homophily_index * 100).toFixed(0) }}%
        </span>
      </div>
    </div>

    <!-- Stacked area chart: opinion distribution over time -->
    <div class="chart-container">
      <span class="chart-label">Opinion Distribution Over Time</span>
      <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="area-chart">
        <!-- Grid lines -->
        <line
          v-for="y in [0, 0.25, 0.5, 0.75, 1]"
          :key="y"
          :x1="padding.left"
          :y1="padding.top + (1 - y) * innerHeight"
          :x2="padding.left + innerWidth"
          :y2="padding.top + (1 - y) * innerHeight"
          stroke="rgba(255,255,255,0.06)"
          stroke-width="0.5"
        />

        <!-- Stacked areas -->
        <polygon
          v-for="area in stackedAreas"
          :key="area.stance"
          :points="area.points"
          :fill="area.color"
          fill-opacity="0.7"
          stroke="none"
        />

        <!-- X-axis labels -->
        <text
          v-for="label in xLabels"
          :key="label.label"
          :x="label.x"
          :y="chartHeight - 5"
          text-anchor="middle"
          fill="rgba(255,255,255,0.4)"
          font-size="10"
        >
          {{ label.label }}
        </text>

        <!-- Y-axis labels -->
        <text
          v-for="y in [0, 50, 100]"
          :key="y"
          :x="padding.left - 5"
          :y="padding.top + (1 - y / 100) * innerHeight + 3"
          text-anchor="end"
          fill="rgba(255,255,255,0.4)"
          font-size="9"
        >
          {{ y }}%
        </text>
      </svg>
    </div>

    <!-- Cluster evolution stream chart (SSE data) -->
    <ClusterEvolutionChart v-if="hasStoreData" :timesteps="timesteps" />

    <!-- Delta sparkline -->
    <div v-if="deltaPath" class="sparkline-container">
      <span class="chart-label">Convergence (max delta)</span>
      <svg :viewBox="`0 0 ${chartWidth} 60`" class="sparkline">
        <path
          :d="deltaPath"
          fill="none"
          stroke="#818cf8"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
    </div>

    <!-- Cluster info -->
    <div v-if="clusters.length > 0" class="cluster-info">
      <span class="chart-label">Opinion Clusters</span>
      <div class="cluster-list">
        <div
          v-for="cluster in clusters"
          :key="cluster.label"
          class="cluster-badge"
        >
          <span class="cluster-size">{{ cluster.size }}</span>
          <span class="cluster-label">Cluster {{ cluster.label + 1 }}</span>
        </div>
      </div>
    </div>

    <!-- Stigmergy Topics (API only) -->
    <div v-if="stigmergyTopics.length > 0" class="stigmergy-section">
      <span class="chart-label">Stigmergy Topics</span>
      <div class="topic-list">
        <div
          v-for="topic in stigmergyTopics"
          :key="topic.topic"
          class="topic-badge"
        >
          <span class="topic-name">{{ topic.topic }}</span>
          <span class="topic-intensity">{{ topic.intensity.toFixed(1) }}</span>
        </div>
      </div>
    </div>

    <!-- Prediction Market (API only) -->
    <div v-if="Object.keys(predictionMarket).length > 0" class="prediction-market-section">
      <span class="chart-label">Prediction Market</span>
      <div class="market-bars">
        <div
          v-for="(price, outcome) in predictionMarket"
          :key="outcome"
          class="market-bar-row"
        >
          <span class="market-outcome">{{ outcome }}</span>
          <div class="market-bar-track">
            <div
              class="market-bar-fill"
              :style="{ width: (Number(price) * 100) + '%', backgroundColor: stanceColors[String(outcome)] || '#818cf8' }"
            />
          </div>
          <span class="market-price">{{ (Number(price) * 100).toFixed(1) }}%</span>
        </div>
      </div>
    </div>

    <!-- Phase Transitions & Tipping Points (API only) -->
    <div v-if="phaseTransitions.length > 0 || tippingPoints.length > 0" class="events-section">
      <span class="chart-label">Emergent Events</span>
      <div class="event-list">
        <div v-for="pt in phaseTransitions" :key="'pt' + pt.timestep" class="event-badge split">
          t{{ pt.timestep }}: {{ pt.type }}
        </div>
        <div v-for="tp in tippingPoints" :key="'tp' + tp.timestep" class="event-badge cascade">
          t{{ tp.timestep }}: cascade ({{ (tp.cascade_ratio * 100).toFixed(0) }}%)
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.propagation-dashboard {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.02);
  border-radius: var(--radius-md, 8px);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.dashboard-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.metrics-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.5rem 0.75rem;
  background: rgba(255, 255, 255, 0.04);
  border-radius: var(--radius-sm, 4px);
  min-width: 80px;
}

.metric-label {
  font-size: 0.7rem;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.4));
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.metric-value {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-value.converged {
  color: #22c55e;
}

.metric-value.warning {
  color: #f59e0b;
}

.chart-container,
.sparkline-container {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.chart-label {
  font-size: 0.72rem;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.4));
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.area-chart {
  width: 100%;
  height: auto;
}

.sparkline {
  width: 100%;
  height: 40px;
}

.cluster-info {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.cluster-list {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.cluster-badge {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.6rem;
  background: rgba(99, 102, 241, 0.15);
  border-radius: var(--radius-sm, 4px);
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.cluster-size {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 700;
  color: #818cf8;
}

.cluster-label {
  font-size: 0.72rem;
  color: var(--text-secondary);
}

/* Stigmergy */
.stigmergy-section,
.prediction-market-section,
.events-section {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.topic-list {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.topic-badge {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.25rem 0.5rem;
  background: rgba(245, 158, 11, 0.12);
  border-radius: var(--radius-sm, 4px);
  border: 1px solid rgba(245, 158, 11, 0.3);
  font-size: 0.78rem;
}

.topic-name { color: var(--text-primary); }
.topic-intensity { font-family: var(--font-mono); color: #f59e0b; font-weight: 600; }

/* Prediction Market */
.market-bars {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.market-bar-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.market-outcome {
  font-size: 0.75rem;
  color: var(--text-secondary);
  min-width: 90px;
  text-align: right;
}

.market-bar-track {
  flex: 1;
  height: 14px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 3px;
  overflow: hidden;
}

.market-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}

.market-price {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 45px;
}

/* Events */
.event-list {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.event-badge {
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm, 4px);
  font-size: 0.72rem;
  font-family: var(--font-mono);
}

.event-badge.split {
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.event-badge.cascade {
  background: rgba(168, 85, 247, 0.12);
  border: 1px solid rgba(168, 85, 247, 0.3);
  color: #a855f7;
}
</style>
