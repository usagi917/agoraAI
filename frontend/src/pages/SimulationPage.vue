<script setup lang="ts">
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSimulation, getSimulationGraph, type SimulationResponse } from '../api/client'
import { useSimulationStore } from '../stores/simulationStore'
import { useSimulationSSE } from '../composables/useSimulationSSE'
import { useGraphStore } from '../stores/graphStore'
import { useForceGraph } from '../composables/useForceGraph'
import SimulationProgress from '../components/SimulationProgress.vue'
import ColonyGrid from '../components/ColonyGrid.vue'

const route = useRoute()
const router = useRouter()
const simId = route.params.id as string

const sim = ref<SimulationResponse | null>(null)
const graphContainer = ref<HTMLElement | null>(null)
const selectedEntity = ref<any>(null)
const elapsedTime = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

const store = useSimulationStore()
const graphStore = useGraphStore()
const { graph, setFullGraph, resetCamera } = useForceGraph(graphContainer)

let sse: ReturnType<typeof useSimulationSSE> | null = null

const entityTypeColors: Record<string, string> = {
  organization: '#4FC3F7',
  person: '#FFB74D',
  policy: '#81C784',
  market: '#E57373',
  technology: '#BA68C8',
  resource: '#4DB6AC',
}

const formattedTime = computed(() => {
  const m = Math.floor(elapsedTime.value / 60)
  const s = elapsedTime.value % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
})

onMounted(async () => {
  sim.value = await getSimulation(simId)
  store.init(simId, sim.value.mode as any, sim.value.prompt_text)

  if (sim.value.status === 'completed') {
    store.setStatus('completed')
    store.setPhase('completed')
    const graphData = await getSimulationGraph(simId)
    if (graphData.nodes?.length) {
      graphStore.setFullState(graphData.nodes, graphData.edges)
      await nextTick()
      setFullGraph(graphData.nodes, graphData.edges)
    }
    return
  }

  sse = useSimulationSSE(simId)
  sse.start()
  timer = setInterval(() => { elapsedTime.value++ }, 1000)
})

// SSE イベントの監視
watch(
  () => store.status,
  (newStatus) => {
    if (newStatus === 'completed' || newStatus === 'failed') {
      if (timer) { clearInterval(timer); timer = null }
    }
  },
)

// グラフの差分適用を監視
watch(
  () => graphStore.nodes.length + graphStore.edges.length,
  () => {
    if (graphStore.nodes.length > 0 && graph.value) {
      setFullGraph(graphStore.nodes, graphStore.edges)
    }
  },
)

watch(graph, (fg) => {
  if (!fg) return
  fg.onNodeClick((node: any) => {
    const storeNode = graphStore.nodes.find((n: any) => n.id === node.id)
    selectedEntity.value = storeNode || node
    const distance = 100
    const distRatio = 1 + distance / Math.hypot(node.x || 0, node.y || 0, node.z || 0)
    fg.cameraPosition(
      { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
      { x: node.x, y: node.y, z: node.z },
      1000,
    )
  })
})

function goToResults() {
  router.push(`/sim/${simId}/results`)
}
</script>

<template>
  <div class="sim-page">
    <!-- Progress Pipeline -->
    <SimulationProgress />

    <!-- Status Bar -->
    <div class="status-bar">
      <div class="status-left">
        <span class="status-mono">{{ graphStore.nodes.length }} nodes / {{ graphStore.edges.length }} edges</span>
        <span class="status-divider">|</span>
        <span class="status-mono">{{ formattedTime }}</span>
        <template v-if="store.isSwarmMode">
          <span class="status-divider">|</span>
          <span class="status-mono">{{ store.completedColonies }}/{{ store.colonies.length }} Colony</span>
        </template>
      </div>
      <div class="status-right">
        <button
          v-if="store.status === 'completed'"
          class="btn btn-primary"
          @click="goToResults"
        >
          結果を表示
        </button>
      </div>
    </div>

    <div v-if="store.error" class="error-banner">
      {{ store.error }}
    </div>

    <!-- Main Layout -->
    <div class="sim-layout">
      <!-- Left: Graph + Colony Grid -->
      <div class="main-panel">
        <div class="graph-panel">
          <div class="panel-header">
            <h3>3D Knowledge Graph</h3>
            <div class="panel-metrics">
              <span class="metric"><span class="metric-val">{{ graphStore.nodes.length }}</span> nodes</span>
              <span class="metric"><span class="metric-val">{{ graphStore.edges.length }}</span> edges</span>
            </div>
          </div>
          <div ref="graphContainer" class="graph-container">
            <div v-if="graphStore.nodes.length === 0" class="graph-empty">
              <div class="loading-dots"><span></span><span></span><span></span></div>
              <p>グラフデータ待機中...</p>
            </div>
          </div>
          <button v-if="graphStore.nodes.length > 0" class="reset-camera-btn" @click="resetCamera" title="中心に戻す">&#8962;</button>
          <div v-if="graphStore.nodes.length > 0" class="graph-legend">
            <span class="legend-item" v-for="(color, type) in entityTypeColors" :key="type">
              <span class="legend-dot" :style="{ background: color, boxShadow: `0 0 6px ${color}` }"></span>
              <span class="legend-label">{{ type }}</span>
            </span>
          </div>
        </div>

        <!-- Colony Grid (swarm/hybrid only) -->
        <div v-if="store.isSwarmMode && store.colonies.length > 0" class="colony-overlay">
          <div class="panel-header">
            <h3>Colony Grid</h3>
            <span class="panel-count">{{ store.completedColonies }}/{{ store.colonies.length }}</span>
          </div>
          <ColonyGrid :colonies="store.colonies" />
        </div>
      </div>

      <!-- Right: Side Panel -->
      <div class="side-panel">
        <!-- Entity Detail -->
        <div v-if="selectedEntity" class="panel-card entity-detail">
          <div class="panel-header">
            <h3>Entity Inspector</h3>
            <button class="btn-icon" @click="selectedEntity = null">&#10005;</button>
          </div>
          <div class="entity-name">{{ selectedEntity.label }}</div>
          <div class="entity-meta">
            <span class="entity-type-badge">{{ selectedEntity.type }}</span>
            <span class="entity-score">重要度 {{ ((selectedEntity.importance_score || 0) * 100).toFixed(0) }}%</span>
          </div>
          <div class="detail-grid">
            <div v-if="selectedEntity.stance" class="detail-item">
              <span class="detail-key">立場</span>
              <span class="detail-val">{{ selectedEntity.stance }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-key">ステータス</span>
              <span class="detail-val">{{ selectedEntity.status }}</span>
            </div>
          </div>
        </div>

        <!-- Prompt Info -->
        <div v-if="sim?.prompt_text" class="panel-card">
          <div class="panel-header"><h3>Prompt</h3></div>
          <p class="prompt-text">{{ sim.prompt_text }}</p>
        </div>

        <!-- Console -->
        <div class="panel-card console-panel">
          <div class="panel-header">
            <h3>Console</h3>
            <span class="panel-count" :class="{ live: store.status === 'running' }">
              {{ store.status === 'running' ? 'LIVE' : store.status.toUpperCase() }}
            </span>
          </div>
          <div class="console-output">
            <div v-if="store.status === 'running' || store.status === 'generating_report'" class="console-cursor">&#9608;</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sim-page { display: flex; flex-direction: column; gap: var(--section-gap); }

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.75rem var(--panel-padding);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.status-left {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  font-family: var(--font-mono);
  font-size: 0.78rem;
}

.status-divider { color: var(--text-muted); }
.status-mono { color: var(--text-secondary); }

.status-right {
  display: flex;
  justify-content: flex-end;
  margin-left: auto;
}

.error-banner { padding: 0.75rem 1.25rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: var(--radius-sm); color: var(--danger); font-size: 0.85rem; }

.sim-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(18rem, 22rem);
  gap: 1rem;
  align-items: start;
  min-height: min(70vh, 52rem);
}

.main-panel { display: flex; flex-direction: column; gap: 0.75rem; }

.graph-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.panel-header h3 { font-size: 0.82rem; font-weight: 600; }
.panel-metrics { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.metric { font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted); }
.metric-val { color: var(--accent); font-weight: 600; }

.graph-container {
  flex: 1;
  min-height: clamp(18rem, 42vw, 32rem);
  background: radial-gradient(ellipse at 30% 40%, #0d0d2b 0%, #060614 50%, #020208 100%);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(100,100,255,0.12);
  position: relative;
  overflow: hidden;
}

.graph-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.75rem; color: var(--text-muted); font-size: 0.82rem; }
.loading-dots { display: flex; gap: 4px; }
.loading-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: typing-dot 1.4s ease-in-out infinite; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

.reset-camera-btn { position: absolute; top: 12px; right: 12px; z-index: 10; width: 32px; height: 32px; border-radius: 6px; border: 1px solid rgba(100,100,255,0.2); background: rgba(10,10,30,0.75); backdrop-filter: blur(8px); color: rgba(200,200,255,0.7); font-size: 1rem; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
.reset-camera-btn:hover { background: rgba(30,30,80,0.85); color: #fff; border-color: rgba(100,100,255,0.4); }

.graph-legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: rgba(10,10,30,0.75);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(100,100,255,0.15);
  border-radius: 6px;
  z-index: 10;
}

.legend-item { display: flex; align-items: center; gap: 0.3rem; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.legend-label { font-family: var(--font-mono); font-size: 0.65rem; color: rgba(200,200,255,0.7); text-transform: uppercase; }

.colony-overlay { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}

.panel-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }
.panel-count { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); background: rgba(255,255,255,0.04); padding: 0.1rem 0.4rem; border-radius: 4px; }
.panel-count.live { color: var(--success); background: rgba(34,197,94,0.1); }

.btn-icon { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.2rem 0.4rem; border-radius: 4px; }
.btn-icon:hover { color: var(--text-primary); background: rgba(255,255,255,0.06); }

.entity-name { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.4rem; }
.entity-meta { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.entity-type-badge { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 4px; background: var(--accent-subtle); color: var(--accent); text-transform: uppercase; }
.entity-score { font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted); }
.detail-grid { display: flex; flex-direction: column; gap: 0.35rem; }
.detail-item { display: flex; justify-content: space-between; padding: 0.35rem 0; border-top: 1px solid var(--border); font-size: 0.8rem; }
.detail-key { color: var(--text-muted); }
.detail-val { color: var(--text-primary); font-weight: 500; }

.prompt-text { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap; }

.console-panel { flex: 1; min-height: 0; }
.console-output {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  line-height: 1.7;
  max-height: min(14rem, 38vh);
  overflow-y: auto;
  background: rgba(0,0,0,0.3);
  border-radius: var(--radius-sm);
  padding: 0.75rem;
  border: 1px solid var(--border);
}

.console-cursor { color: var(--text-muted); animation: breathe 1s step-end infinite; font-size: 0.72rem; }

@media (max-width: 1200px) {
  .sim-layout {
    grid-template-columns: minmax(0, 1fr) minmax(17rem, 20rem);
  }
}

@media (max-width: 900px) {
  .sim-layout {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .status-right {
    margin-left: 0;
  }
}

@media (max-width: 640px) {
  .status-bar {
    align-items: stretch;
  }

  .status-right {
    width: 100%;
  }

  .status-right :deep(.btn) {
    width: 100%;
  }

  .graph-panel,
  .colony-overlay,
  .panel-card {
    padding: 0.95rem;
  }

  .graph-container {
    min-height: 18rem;
  }

  .reset-camera-btn {
    top: 10px;
    right: 10px;
  }

  .graph-legend {
    left: 10px;
    right: 10px;
    bottom: 10px;
  }

  .entity-meta,
  .detail-item {
    flex-wrap: wrap;
    gap: 0.35rem;
  }
}
</style>
