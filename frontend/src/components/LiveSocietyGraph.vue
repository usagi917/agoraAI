<script setup lang="ts">
import { ref, computed, onUnmounted, watch } from 'vue'
import { useSocietyGraphStore } from '../stores/societyGraphStore'
import { useKGEvolutionStore } from '../stores/kgEvolutionStore'
import { useSimulationStore } from '../stores/simulationStore'
import { STANCE_COLORS } from '../constants/stances'
import { societyPhaseLabel, unifiedPhaseLabel } from '../constants/phases'
import ConversationToast from './ConversationToast.vue'
import NodeDetailPanel from './NodeDetailPanel.vue'
import TemporalSlider from './TemporalSlider.vue'
import ForceGraph2D from './ForceGraph2D.vue'
import GraphSettingsPanel from './GraphSettingsPanel.vue'
import { DEFAULT_PHYSICS, RELATION_EDGE_COLORS, type GraphPhysics } from './forceGraphHelpers'
import { derivePulseUpdate, type PulseCursor } from './liveGraphPulses'

interface GraphEdgePayload {
  id?: string
  source: string
  target: string
  relation_type: string
  weight: number
}

const RELATION_TYPE_STYLES: Record<string, { color: string; width: number; particleColor: string }> = {
  friend: { color: RELATION_EDGE_COLORS.friend, width: 1.4, particleColor: '#8fc4e0' },
  family: { color: RELATION_EDGE_COLORS.family, width: 1.6, particleColor: '#e0c9a0' },
  colleague: { color: RELATION_EDGE_COLORS.colleague, width: 1.2, particleColor: '#a0cbb8' },
  neighbor: { color: RELATION_EDGE_COLORS.neighbor, width: 1.1, particleColor: '#94cbcf' },
  acquaintance: { color: RELATION_EDGE_COLORS.acquaintance, width: 0.9, particleColor: '#b8c2d0' },
  mentions: { color: RELATION_EDGE_COLORS.mentions, width: 1.0, particleColor: '#b8aed8' },
  default: { color: RELATION_EDGE_COLORS.default, width: 1.0, particleColor: '#b0bccc' },
}

const props = defineProps<{
  simulationId: string
  spotlightAgentId?: string | null
}>()

const emit = defineEmits<{
  (e: 'select-agent', agentId: string): void
}>()

const store = useSimulationStore()
const societyGraphStore = useSocietyGraphStore()
const kgStore = useKGEvolutionStore()
const selectedAgentId = ref<string | null>(null)
const highlightedAgentIds = ref<string[]>([])
const graphPhysics = ref<GraphPhysics>({ ...DEFAULT_PHYSICS })
const showPhysicsPanel = ref(false)

const graphRef = ref<InstanceType<typeof ForceGraph2D> | null>(null)
// Cursor into the streaming argument buffer so each update only scans newly
// appended dialogue (O(new) per SSE event, not O(n²) over the whole round).
let pulseCursor: PulseCursor = { round: -1, count: 0 }

watch(
  [() => societyGraphStore.currentArguments.length, () => societyGraphStore.currentRound],
  () => {
    const { pulses, cursor } = derivePulseUpdate(
      societyGraphStore.currentArguments,
      societyGraphStore.currentRound,
      societyGraphStore.liveAgents.values(),
      pulseCursor,
    )
    pulseCursor = cursor
    for (const pulse of pulses) {
      graphRef.value?.firePulse?.(pulse.sourceId, pulse.targetId)
    }
  },
)

const selectedGraphNodeId = computed(() => selectedAgentId.value ?? props.spotlightAgentId ?? null)

const phaseLabel = computed(() => {
  // Unified mode phase labels
  if (store.isUnifiedMode) {
    return unifiedPhaseLabel(store.unifiedPhase, societyGraphStore.currentRound)
  }
  return societyPhaseLabel(store.societyPhase, societyGraphStore.currentRound)
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
    sourceId: e.sourceId,
    targetId: e.targetId,
  }
})

const edgeConversation = computed(() => {
  const info = selectedEdgeInfo.value
  if (!info) return []
  return societyGraphStore.getConversationBetween(info.sourceId, info.targetId)
})

const edgeInteractionCount = computed(() => {
  const info = selectedEdgeInfo.value
  if (!info) return 0
  return societyGraphStore.getInteractionCount(info.sourceId, info.targetId)
})

function clearSelection() {
  selectedAgentId.value = null
  highlightedAgentIds.value = []
}

function clearEdgeSelection() {
  societyGraphStore.setSelectedEdge(null)
}

function handleHighlightAgents(agentIds: string[]) {
  highlightedAgentIds.value = agentIds
}

function handleNodeSelect(node: { id: string }) {
  highlightedAgentIds.value = []
  if (node.id.startsWith('kg-')) {
    selectedAgentId.value = node.id
    return
  }
  emit('select-agent', node.id)
  selectedAgentId.value = node.id
}

function handleBackgroundClick() {
  clearSelection()
  clearEdgeSelection()
}

function handleEdgeHover(edge: GraphEdgePayload | null) {
  if (!edge) {
    societyGraphStore.setHoveredEdge(null)
    return
  }
  societyGraphStore.setHoveredEdge({
    id: edge.id || `${edge.source}:${edge.target}`,
    relationType: edge.relation_type,
    weight: edge.weight,
    sourceId: edge.source,
    targetId: edge.target,
  })
}

function handleEdgeSelect(edge: GraphEdgePayload) {
  societyGraphStore.setSelectedEdge({
    id: edge.id || `${edge.source}:${edge.target}`,
    relationType: edge.relation_type,
    weight: edge.weight,
    sourceId: edge.source,
    targetId: edge.target,
  })
}

// Time scrubber for KG replay
const scrubberPlaying = ref(false)
const showScrubber = computed(() =>
  kgStore.layerVisible && kgStore.maxRound > 0 && store.status === 'completed',
)
const scrubberRound = computed({
  get: () => kgStore.replayRound ?? Math.max(0, kgStore.maxRound),
  set: (round: number) => onScrubberChange(round),
})

const KG_REPLAY_INTERVAL_MS = 900
let scrubberTimer: ReturnType<typeof window.setInterval> | null = null

function stopScrubberPlayback() {
  if (scrubberTimer !== null) {
    window.clearInterval(scrubberTimer)
    scrubberTimer = null
  }
}

function onScrubberChange(round: number) {
  kgStore.setReplayRound(round)
}

function advanceScrubberPlayback() {
  if (scrubberRound.value >= kgStore.maxRound) {
    scrubberPlaying.value = false
    stopScrubberPlayback()
    return
  }

  onScrubberChange(scrubberRound.value + 1)

  if (scrubberRound.value >= kgStore.maxRound) {
    scrubberPlaying.value = false
    stopScrubberPlayback()
  }
}

watch(scrubberPlaying, (playing) => {
  if (!playing) {
    stopScrubberPlayback()
    return
  }

  if (!showScrubber.value) {
    scrubberPlaying.value = false
    return
  }

  if (scrubberRound.value >= kgStore.maxRound) {
    onScrubberChange(0)
  }

  stopScrubberPlayback()
  scrubberTimer = window.setInterval(advanceScrubberPlayback, KG_REPLAY_INTERVAL_MS)
})

watch(showScrubber, (visible) => {
  if (!visible) {
    scrubberPlaying.value = false
    kgStore.clearReplayRound()
  }
})

onUnmounted(() => {
  stopScrubberPlayback()
  pulseCursor = { round: -1, count: 0 }
  societyGraphStore.reset()
  kgStore.reset()
})
</script>

<template>
  <div class="live-society-graph">
    <ForceGraph2D
      ref="graphRef"
      :nodes="societyGraphStore.graphNodes"
      :edges="societyGraphStore.graphEdges"
      :selected-node-id="selectedGraphNodeId"
      :highlighted-node-ids="highlightedAgentIds"
      :physics="graphPhysics"
      @select-node="handleNodeSelect"
      @hover-edge="handleEdgeHover"
      @select-edge="handleEdgeSelect"
      @background-click="handleBackgroundClick"
    />

    <!-- Physics settings -->
    <button
      v-if="societyGraphStore.nodeCount > 0"
      class="physics-toggle"
      :class="{ active: showPhysicsPanel }"
      title="グラフ物理設定"
      data-testid="physics-toggle"
      @click="showPhysicsPanel = !showPhysicsPanel"
    >⚙</button>
    <div v-if="showPhysicsPanel" class="physics-panel">
      <GraphSettingsPanel
        :physics="graphPhysics"
        @update:physics="graphPhysics = $event"
      />
    </div>

    <!-- Empty state (before selection) -->
    <div
      v-if="societyGraphStore.nodeCount === 0"
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
        <span class="legend-dot" :style="{ background: color, boxShadow: `0 0 3px ${color}` }" />
        <span class="legend-label">{{ stance }}</span>
      </div>
      <!-- Edge type legend -->
      <div class="legend-divider" />
      <div v-for="[type, style] in edgeLegend" :key="type" class="legend-item">
        <span class="legend-line" :style="{ background: style.color, boxShadow: `0 0 2px ${style.color}` }" />
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
          <span v-if="edgeInteractionCount > 0" class="meta-chip interaction-chip">
            {{ edgeInteractionCount }} interactions
          </span>
        </div>
        <!-- Conversation transcript -->
        <div v-if="edgeConversation.length > 0" class="edge-transcript">
          <div class="transcript-header">Conversation</div>
          <div class="transcript-scroll">
            <div
              v-for="(arg, i) in edgeConversation"
              :key="i"
              class="transcript-entry"
            >
              <span class="transcript-speaker">{{ arg.participant_name }}</span>
              <span class="transcript-text">{{ arg.argument.length > 120 ? arg.argument.slice(0, 117) + '...' : arg.argument }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Layer toggles -->
    <div v-if="kgStore.entityCount > 0 || societyGraphStore.populationNodeCount > 0" class="layer-toggles">
      <button
        v-if="societyGraphStore.populationNodeCount > 0"
        class="layer-btn"
        :class="{ active: societyGraphStore.populationVisible }"
        title="全人口レイヤー"
        data-testid="population-toggle"
        @click="societyGraphStore.populationVisible = !societyGraphStore.populationVisible"
      >人口</button>
      <button
        class="layer-btn"
        :class="{ active: societyGraphStore.socialEdgesVisible }"
        title="ソーシャルエッジ"
        @click="societyGraphStore.socialEdgesVisible = !societyGraphStore.socialEdgesVisible"
      >社会</button>
      <button
        class="layer-btn"
        :class="{ active: kgStore.layerVisible }"
        title="ナレッジグラフ"
        @click="kgStore.toggleLayerVisible()"
      >知識</button>
      <button
        class="layer-btn"
        :class="{ active: societyGraphStore.agentEntityLinksVisible }"
        title="エージェント⇔エンティティリンク"
        @click="societyGraphStore.agentEntityLinksVisible = !societyGraphStore.agentEntityLinksVisible"
      >リンク</button>
    </div>

    <!-- KG Time scrubber -->
    <div v-if="showScrubber" class="kg-scrubber">
      <TemporalSlider
        :total-rounds="kgStore.maxRound"
        v-model="scrubberRound"
        :playing="scrubberPlaying"
        @update:model-value="onScrubberChange"
        @update:playing="scrubberPlaying = $event"
      />
    </div>

    <!-- KG stats badge -->
    <div v-if="kgStore.layerVisible && kgStore.entityCount > 0" class="kg-stats-badge">
      <span class="kg-badge-label">KG</span>
      <span class="kg-badge-count">{{ kgStore.entityCount }} entities</span>
      <span class="kg-badge-count">{{ kgStore.relationCount }} relations</span>
    </div>

    <!-- Population stats badge -->
    <div
      v-if="societyGraphStore.populationVisible && societyGraphStore.populationNodeCount > 0"
      class="kg-stats-badge population-stats-badge"
      data-testid="population-stats"
    >
      <span class="kg-badge-label">人口</span>
      <span class="kg-badge-count">{{ societyGraphStore.populationNodeCount.toLocaleString() }} 人</span>
    </div>

    <!-- Conversation toast -->
    <ConversationToast
      v-if="showConversationToast"
      :arguments="societyGraphStore.currentArguments"
      :round="societyGraphStore.currentRound"
    />

    <!-- Node detail panel: KG nodes only (agent nodes open drawer in parent) -->
    <div v-if="selectedAgentId?.startsWith('kg-')" class="agent-detail-overlay">
      <NodeDetailPanel
        :node-id="selectedAgentId"
        @close="clearSelection"
        @highlight-agents="handleHighlightAgents"
        @select-agent="emit('select-agent', $event)"
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

.graph-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  pointer-events: none;
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
  background: linear-gradient(90deg, #5aa0c8, #6faa8f);
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

.layer-toggles {
  position: absolute;
  top: 0.75rem;
  right: 3rem;
  margin-top: 1.4rem;
  display: flex;
  gap: 0.35rem;
  z-index: 5;
}

.physics-toggle {
  position: absolute;
  top: 2.15rem;
  right: 0.75rem;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  font-size: 0.85rem;
  color: rgba(200, 200, 220, 0.4);
  cursor: pointer;
  background: rgba(16, 16, 30, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  transition: all 0.2s;
}

.physics-toggle:hover {
  color: rgba(230, 230, 245, 0.7);
  background: rgba(30, 30, 50, 0.9);
}

.physics-toggle.active {
  color: rgba(138, 127, 191, 0.95);
  background: rgba(138, 127, 191, 0.12);
  border-color: rgba(138, 127, 191, 0.45);
}

.physics-panel {
  position: absolute;
  top: 3.9rem;
  right: 0.75rem;
  z-index: 10;
  pointer-events: auto;
}

.layer-btn {
  min-width: 3rem;
  height: 1.75rem;
  padding: 0 0.55rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  font-family: var(--font-mono);
  background: rgba(10, 10, 15, 0.78);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}
.layer-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}
.layer-btn.active {
  border-color: var(--border-active);
  color: var(--accent);
  background: var(--accent-subtle);
}

.kg-scrubber {
  position: absolute;
  bottom: 2.5rem;
  left: 50%;
  transform: translateX(-50%);
  width: min(20rem, 60%);
  z-index: 5;
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
  border: 1px solid rgba(138, 127, 191, 0.25);
  border-radius: 6px;
  z-index: 5;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: rgba(200, 200, 255, 0.6);
}

.population-stats-badge {
  bottom: 2.9rem;
  border-color: rgba(90, 160, 200, 0.25);
}

.kg-badge-label {
  color: rgba(138, 127, 191, 0.9);
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
  max-width: 20rem;
}

.interaction-chip {
  border-color: rgba(90, 160, 200, 0.4) !important;
  color: rgba(143, 196, 224, 0.85) !important;
}

.edge-transcript {
  margin-top: 0.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: 0.4rem;
}

.transcript-header {
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(180, 180, 200, 0.5);
  margin-bottom: 0.3rem;
}

.transcript-scroll {
  max-height: 10rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.transcript-entry {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.3rem 0.4rem;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 4px;
  border-left: 2px solid rgba(100, 187, 106, 0.4);
}

.transcript-speaker {
  font-size: 0.6rem;
  font-weight: 600;
  color: rgba(100, 187, 106, 0.8);
}

.transcript-text {
  font-size: 0.65rem;
  color: rgba(200, 200, 220, 0.7);
  line-height: 1.3;
}

.transcript-scroll::-webkit-scrollbar {
  width: 3px;
}
.transcript-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}
</style>
