<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useLiveSocietyGraph } from '../composables/useLiveSocietyGraph'
import { useSocietyGraphStore, STANCE_COLORS } from '../stores/societyGraphStore'
import { useKGEvolutionStore } from '../stores/kgEvolutionStore'
import { RELATION_TYPE_STYLES } from '../composables/useForceGraph'
import { useSimulationStore } from '../stores/simulationStore'
import type { ThinkingVisualMode } from '../composables/useThinkingParticles'
import ConversationToast from './ConversationToast.vue'
import NodeDetailPanel from './NodeDetailPanel.vue'

defineProps<{
  simulationId: string
}>()

const graphContainer = ref<HTMLElement | null>(null)
const store = useSimulationStore()
const societyGraphStore = useSocietyGraphStore()
const kgStore = useKGEvolutionStore()

const thinkingMode = computed<ThinkingVisualMode>(() => {
  if (store.phase === 'report' || store.status === 'generating_report') return 'report'
  return 'society'
})

const { selectedAgentId, resetCamera, graphError, toggleBloom, bloomEnabled } = useLiveSocietyGraph(graphContainer, thinkingMode)

const phaseLabel = computed(() => {
  // Unified mode phase labels
  if (store.isUnifiedMode) {
    switch (store.unifiedPhase) {
      case 'society_pulse': return '社会の脈動を測定中'
      case 'council': return `評議会 Round ${societyGraphStore.currentRound}`
      case 'synthesis': return '分析を統合中'
      case 'completed': return 'Completed'
      default: return 'Unified Simulation'
    }
  }
  const phase = store.societyPhase
  switch (phase) {
    case 'population': return 'Population Generation'
    case 'selection': return 'Agent Selection'
    case 'activation': return 'Activation Layer'
    case 'evaluation': return 'Evaluation'
    case 'meeting': return `Meeting Round ${societyGraphStore.currentRound}`
    case 'completed': return 'Completed'
    default: return 'Society Simulation'
  }
})

const showConversationToast = computed(() =>
  societyGraphStore.currentArguments.length > 0,
)

const stanceLegend = Object.entries(STANCE_COLORS)
const socialRelTypes = ['friend', 'family', 'colleague', 'neighbor', 'acquaintance']
const edgeLegend = Object.entries(RELATION_TYPE_STYLES).filter(([k]) => socialRelTypes.includes(k))

const hoveredEdgeInfo = computed(() => {
  const e = societyGraphStore.hoveredEdge
  if (!e) return null
  const src = societyGraphStore.liveAgents.get(e.sourceId)
  const tgt = societyGraphStore.liveAgents.get(e.targetId)
  return {
    relationType: e.relationType,
    weight: e.weight,
    sourceName: src?.displayName || src?.label || e.sourceId,
    targetName: tgt?.displayName || tgt?.label || e.targetId,
  }
})

const selectedEdgeInfo = computed(() => {
  const e = societyGraphStore.selectedEdge
  if (!e) return null
  const src = societyGraphStore.liveAgents.get(e.sourceId)
  const tgt = societyGraphStore.liveAgents.get(e.targetId)
  return {
    relationType: e.relationType,
    weight: e.weight,
    sourceName: src?.displayName || src?.label || e.sourceId,
    targetName: tgt?.displayName || tgt?.label || e.targetId,
    color: (RELATION_TYPE_STYLES[e.relationType] || RELATION_TYPE_STYLES.default).color,
  }
})

function clearSelection() {
  selectedAgentId.value = null
}

function clearEdgeSelection() {
  societyGraphStore.setSelectedEdge(null)
}

function handleHighlightAgents(_agentIds: string[]) {
  // Phase 3.2: Will implement dim/highlight logic in useLiveSocietyGraph
}

onUnmounted(() => {
  societyGraphStore.reset()
  kgStore.reset()
})
</script>

<template>
  <div class="live-society-graph">
    <!-- 3D Canvas -->
    <div ref="graphContainer" class="graph-canvas-host" />

    <!-- Error -->
    <div v-if="graphError" class="graph-overlay error-overlay">
      <p>{{ graphError }}</p>
    </div>

    <!-- Empty state (before selection) -->
    <div
      v-else-if="societyGraphStore.nodeCount === 0"
      class="graph-overlay empty-overlay"
    >
      <div class="empty-shell">
        <div class="empty-eyebrow">{{ phaseLabel }}</div>
        <div class="empty-title">
          {{ store.isUnifiedMode
            ? (store.unifiedPhase === 'society_pulse'
              ? '1,000人の社会反応を測定しています'
              : '評議会メンバーを準備しています')
            : (store.societyPhase === 'population'
              ? '1,000人のデジタル住民を生成しています'
              : 'エージェントを選抜しています')
          }}
        </div>
        <div class="loading-dots"><span /><span /><span /></div>
      </div>
    </div>

    <!-- Phase badge -->
    <div v-if="societyGraphStore.nodeCount > 0" class="phase-badge">
      <span class="phase-dot" />
      {{ phaseLabel }}
    </div>

    <!-- Stats -->
    <div v-if="societyGraphStore.nodeCount > 0" class="graph-stats">
      <span>{{ societyGraphStore.nodeCount }} agents</span>
      <span class="stats-divider">/</span>
      <span>{{ societyGraphStore.edgeCount }} edges</span>
    </div>

    <!-- Activation progress -->
    <div
      v-if="store.societyPhase === 'activation' && societyGraphStore.activationTotal > 0"
      class="activation-progress"
    >
      <div
        class="activation-bar"
        :style="{ width: `${(societyGraphStore.activationCompleted / societyGraphStore.activationTotal) * 100}%` }"
      />
      <span class="activation-label">
        {{ societyGraphStore.activationCompleted }}/{{ societyGraphStore.activationTotal }}
      </span>
    </div>

    <!-- Stance legend -->
    <div v-if="societyGraphStore.nodeCount > 0" class="stance-legend">
      <div v-for="[stance, color] in stanceLegend" :key="stance" class="legend-item">
        <span class="legend-dot" :style="{ background: color, boxShadow: `0 0 6px ${color}` }" />
        <span class="legend-label">{{ stance }}</span>
      </div>
      <!-- Edge type legend -->
      <div class="legend-divider" />
      <div v-for="[type, style] in edgeLegend" :key="type" class="legend-item">
        <span class="legend-line" :style="{ background: style.color, boxShadow: `0 0 4px ${style.color}` }" />
        <span class="legend-label">{{ type }}</span>
      </div>
    </div>

    <!-- Edge hover tooltip -->
    <div v-if="hoveredEdgeInfo" class="edge-tooltip">
      <span class="edge-tooltip-type" :style="{ color: (RELATION_TYPE_STYLES[hoveredEdgeInfo.relationType] || RELATION_TYPE_STYLES.default).color }">
        {{ hoveredEdgeInfo.relationType }}
      </span>
      <span class="edge-tooltip-names">{{ hoveredEdgeInfo.sourceName }} &harr; {{ hoveredEdgeInfo.targetName }}</span>
      <span class="edge-tooltip-weight">{{ Math.round(hoveredEdgeInfo.weight * 100) }}%</span>
    </div>

    <!-- Edge detail card (on click) -->
    <div v-if="selectedEdgeInfo" class="edge-detail-overlay">
      <div class="agent-detail-card">
        <div class="agent-detail-header">
          <h4>{{ selectedEdgeInfo.sourceName }} &harr; {{ selectedEdgeInfo.targetName }}</h4>
          <button class="btn-close" @click="clearEdgeSelection">&times;</button>
        </div>
        <div class="agent-detail-meta">
          <span class="meta-chip" :style="{ borderColor: selectedEdgeInfo.color, color: selectedEdgeInfo.color }">
            {{ selectedEdgeInfo.relationType }}
          </span>
          <span class="meta-chip">
            Strength {{ Math.round(selectedEdgeInfo.weight * 100) }}%
          </span>
        </div>
      </div>
    </div>

    <!-- Control buttons -->
    <div v-if="societyGraphStore.nodeCount > 0" class="graph-controls">
      <button
        class="graph-ctrl-btn"
        title="中心に戻す"
        @click="resetCamera"
      >
        &#8962;
      </button>
      <button
        class="graph-ctrl-btn"
        :class="{ active: bloomEnabled }"
        title="Bloom エフェクト"
        @click="toggleBloom()"
      >
        &#10022;
      </button>
      <button
        v-if="kgStore.entityCount > 0"
        class="graph-ctrl-btn"
        :class="{ active: kgStore.layerVisible }"
        title="ナレッジグラフ表示"
        @click="kgStore.toggleLayerVisible()"
      >
        KG
      </button>
    </div>

    <!-- KG stats badge -->
    <div v-if="kgStore.layerVisible && kgStore.entityCount > 0" class="kg-stats-badge">
      <span class="kg-badge-label">KG</span>
      <span class="kg-badge-count">{{ kgStore.entityCount }} entities</span>
      <span class="kg-badge-count">{{ kgStore.relationCount }} relations</span>
    </div>

    <!-- Conversation toast -->
    <ConversationToast
      v-if="showConversationToast"
      :arguments="societyGraphStore.currentArguments"
      :round="societyGraphStore.currentRound"
    />

    <!-- Node detail panel (on click) -->
    <div v-if="selectedAgentId" class="agent-detail-overlay">
      <NodeDetailPanel
        :node-id="selectedAgentId"
        @close="clearSelection"
        @highlight-agents="handleHighlightAgents"
      />
    </div>
  </div>
</template>

<style scoped>
.live-society-graph {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

.graph-canvas-host {
  position: absolute;
  inset: 0;
}

.graph-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  pointer-events: none;
}

.error-overlay p {
  color: var(--danger, #ef4444);
  font-size: 0.85rem;
}

.empty-shell {
  max-width: 22rem;
  padding: 1.4rem 1.5rem;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(8, 10, 22, 0.56);
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
  text-align: center;
}

.empty-eyebrow {
  font-size: 0.65rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(150, 200, 150, 0.7);
}

.empty-title {
  font-size: 0.88rem;
  font-weight: 600;
  color: rgba(220, 220, 240, 0.85);
}

.loading-dots {
  display: flex;
  gap: 0.3rem;
}
.loading-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(150, 200, 150, 0.6);
  animation: pulse-dot 1.4s ease-in-out infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1.2); }
}

.phase-badge {
  position: absolute;
  top: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.7rem;
  font-weight: 500;
  padding: 0.3rem 0.75rem;
  background: rgba(16, 16, 30, 0.82);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(100, 187, 106, 0.3);
  border-radius: 20px;
  color: rgba(200, 230, 200, 0.9);
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.phase-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #66bb6a;
  animation: pulse-dot 2s ease-in-out infinite;
}

.graph-stats {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  font-family: var(--font-mono, monospace);
  font-size: 0.68rem;
  color: rgba(180, 180, 200, 0.6);
  z-index: 5;
}

.stats-divider {
  margin: 0 0.25rem;
  color: rgba(120, 120, 140, 0.4);
}

.activation-progress {
  position: absolute;
  top: 2.8rem;
  left: 50%;
  transform: translateX(-50%);
  width: min(80%, 16rem);
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  z-index: 5;
  overflow: hidden;
}

.activation-bar {
  height: 100%;
  background: linear-gradient(90deg, #66bb6a, #00e5ff);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.activation-label {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.6rem;
  color: rgba(180, 180, 200, 0.5);
  font-family: var(--font-mono, monospace);
}

.stance-legend {
  position: absolute;
  bottom: 0.75rem;
  left: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  z-index: 5;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  font-size: 0.65rem;
  color: rgba(200, 200, 220, 0.65);
}

.graph-controls {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  margin-top: 1.4rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  z-index: 5;
}

.graph-ctrl-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  background: rgba(16, 16, 30, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: rgba(200, 200, 220, 0.6);
  cursor: pointer;
  transition: background 0.2s;
}
.graph-ctrl-btn:hover {
  background: rgba(30, 30, 50, 0.9);
  color: rgba(230, 230, 245, 0.8);
}
.graph-ctrl-btn.active {
  border-color: rgba(100, 187, 106, 0.4);
  color: rgba(100, 187, 106, 0.8);
}

.kg-stats-badge {
  position: absolute;
  bottom: 0.75rem;
  right: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.75rem;
  background: rgba(10, 10, 30, 0.8);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(186, 104, 200, 0.25);
  border-radius: 6px;
  z-index: 5;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: rgba(200, 200, 255, 0.6);
}
.kg-badge-label {
  color: rgba(186, 104, 200, 0.9);
  font-weight: 700;
  font-size: 0.7rem;
}
.kg-badge-count {
  color: rgba(200, 200, 255, 0.5);
}

.agent-detail-overlay {
  position: absolute;
  top: 0.75rem;
  left: 0.75rem;
  z-index: 10;
  pointer-events: auto;
}

.agent-detail-card {
  max-width: 16rem;
  padding: 0.75rem 1rem;
  background: rgba(16, 16, 30, 0.92);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(100, 187, 106, 0.25);
  border-radius: 10px;
}

.agent-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.agent-detail-header h4 {
  font-size: 0.82rem;
  font-weight: 600;
  color: rgba(220, 220, 240, 0.9);
  margin: 0;
}

.btn-close {
  background: none;
  border: none;
  color: rgba(200, 200, 220, 0.5);
  font-size: 1.1rem;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}
.btn-close:hover { color: rgba(230, 230, 245, 0.9); }

.agent-detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-top: 0.4rem;
}

.meta-chip {
  font-size: 0.65rem;
  padding: 0.1rem 0.4rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  color: rgba(200, 200, 220, 0.7);
}

.agent-stance {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.stance-badge {
  font-size: 0.68rem;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  color: #111;
  font-weight: 600;
}

.confidence {
  font-size: 0.68rem;
  color: rgba(200, 200, 220, 0.6);
  font-family: var(--font-mono, monospace);
}

.agent-speech {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.agent-speech p {
  font-size: 0.75rem;
  line-height: 1.5;
  color: rgba(220, 220, 240, 0.8);
  margin: 0;
}

.legend-divider {
  width: 100%;
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
  margin: 0.2rem 0;
}

.legend-line {
  width: 16px;
  height: 2px;
  border-radius: 1px;
  flex-shrink: 0;
}

.edge-tooltip {
  position: absolute;
  bottom: 0.75rem;
  right: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.7rem;
  background: rgba(16, 16, 30, 0.88);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  z-index: 10;
  pointer-events: none;
}

.edge-tooltip-type {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: capitalize;
}

.edge-tooltip-names {
  font-size: 0.65rem;
  color: rgba(200, 200, 220, 0.7);
}

.edge-tooltip-weight {
  font-size: 0.65rem;
  color: rgba(180, 180, 200, 0.5);
  font-family: var(--font-mono, monospace);
}

.edge-detail-overlay {
  position: absolute;
  bottom: 3rem;
  right: 0.75rem;
  z-index: 10;
  pointer-events: auto;
}
</style>
