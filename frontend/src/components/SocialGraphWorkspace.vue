<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useSlots } from 'vue'

import { bootstrapGraphActivity } from '../services/graphActivitySync'
import { focusGraphActivityEvent } from '../services/graphActivityAdapter'
import { useSocialGraphActivityStore } from '../stores/socialGraphActivityStore'
import { useSocialGraphTopologyStore } from '../stores/socialGraphTopologyStore'
import { useSocialGraphViewStore } from '../stores/socialGraphViewStore'
import SigmaSocialGraph from './SigmaSocialGraph.vue'

const props = withDefaults(defineProps<{
  simulationId: string
  mode: 'live' | 'replay' | 'readonly'
  autoBootstrap?: boolean
}>(), {
  autoBootstrap: true,
})

const topology = useSocialGraphTopologyStore()
const activity = useSocialGraphActivityStore()
const view = useSocialGraphViewStore()
const loading = ref(false)
const error = ref('')
const isMobile = ref(false)
const slots = useSlots()
let bootstrapAbort: AbortController | null = null
let mobileQuery: MediaQueryList | null = null

const projectedNodes = computed(() => {
  const projection = new Map(
    Array.from(topology.nodes.entries()).map(([id, node]) => [id, { ...node }]),
  )
  if (activity.isFollowingLive) return projection
  for (const event of [...activity.events].reverse()) {
    if (event.id <= activity.cursorId || !event.source_id) continue
    const node = projection.get(event.source_id)
    if (!node) continue
    if (event.kind === 'stance_shift') {
      projection.set(event.source_id, {
        ...node,
        stance: String(event.payload.before_stance ?? node.stance),
        activity: 0,
      })
    } else if (event.kind === 'node_status') {
      projection.set(event.source_id, {
        ...node,
        status: event.payload.status === 'activated' ? 'selected' : node.status,
        activity: 0,
      })
    }
  }
  return projection
})
const projectedEdges = computed(() => {
  const projection = new Map(
    Array.from(topology.edges.entries()).map(([id, edge]) => [id, { ...edge }]),
  )
  if (activity.isFollowingLive) return projection
  for (const event of [...activity.events].reverse()) {
    if (event.id <= activity.cursorId || event.kind !== 'relationship_changed' || !event.edge_id) continue
    if (event.payload.is_new) {
      projection.delete(event.edge_id)
      continue
    }
    const edge = projection.get(event.edge_id)
    if (edge) projection.set(event.edge_id, {
      ...edge,
      strength: Number(event.payload.before_strength ?? edge.strength),
      activity: 0,
    })
  }
  return projection
})
const selectedNode = computed(() => (
  view.selectedNodeId ? projectedNodes.value.get(view.selectedNodeId) ?? null : null
))
const selectedEdge = computed(() => (
  view.selectedEdgeId ? projectedEdges.value.get(view.selectedEdgeId) ?? null : null
))
const normalizedSearch = computed(() => view.searchQuery.trim().toLocaleLowerCase('ja'))
const visibleNodes = computed(() => {
  const query = normalizedSearch.value
  const nodes = Array.from(projectedNodes.value.values())
  if (!query) return nodes
  return nodes.filter((node) => [
    node.id,
    node.demographics?.occupation,
    node.demographics?.region,
    node.stance,
  ].some((value) => String(value ?? '').toLocaleLowerCase('ja').includes(query)))
})
const displayNodes = computed(() => {
  if (!isMobile.value || !view.selectedNodeId) return visibleNodes.value
  const neighborIds = new Set<string>([view.selectedNodeId])
  for (const edge of projectedEdges.value.values()) {
    if (edge.source === view.selectedNodeId) neighborIds.add(edge.target)
    if (edge.target === view.selectedNodeId) neighborIds.add(edge.source)
  }
  return visibleNodes.value.filter((node) => neighborIds.has(node.id))
})
const displayPopulationNetwork = computed(() => {
  const network = topology.populationNetwork
  if (!network || !isMobile.value) return network
  const indexById = new Map(network.nodes.map((node) => [node.id, node.agent_index]))
  const included = new Set<number>()
  const selectedIndex = view.selectedNodeId ? indexById.get(view.selectedNodeId) : undefined
  if (selectedIndex != null) {
    included.add(selectedIndex)
    for (const [source, target] of network.edges) {
      if (source === selectedIndex) included.add(target)
      if (target === selectedIndex) included.add(source)
      if (included.size >= 300) break
    }
  } else {
    const stride = Math.max(1, Math.ceil(network.nodes.length / 300))
    network.nodes.forEach((node, index) => {
      if (index % stride === 0) included.add(node.agent_index)
    })
  }
  const nodes = network.nodes.filter((node) => included.has(node.agent_index))
  const edges = network.edges.filter(([source, target]) => (
    included.has(source) && included.has(target)
  ))
  return {
    population_id: network.population_id,
    node_count: nodes.length,
    edge_count: edges.length,
    nodes,
    edges,
  }
})
const timelineEvents = computed(() => {
  const grouped: typeof activity.events = []
  for (const event of activity.events) {
    const previous = grouped.at(-1)
    const status = event.payload.status
    const previousStatus = previous?.payload.status
    if (
      event.kind === 'node_status'
      && previous?.kind === 'node_status'
      && event.phase === previous.phase
      && event.round === previous.round
      && status === previousStatus
    ) {
      grouped[grouped.length - 1] = {
        ...event,
        payload: {
          ...event.payload,
          grouped_count: Number(previous.payload.grouped_count ?? 1) + 1,
        },
      }
    } else {
      grouped.push({
        ...event,
        payload: event.kind === 'node_status'
          ? { ...event.payload, grouped_count: 1 }
          : event.payload,
      })
    }
  }
  return grouped.slice(-120)
})
const visibleEdges = computed(() => Array.from(projectedEdges.value.values()))
const activeEvent = computed(() => activity.selectedEvent ?? activity.visibleEvents.at(-1) ?? null)
const recentSelectedActivity = computed(() => {
  const nodeId = view.selectedNodeId
  const edgeId = view.selectedEdgeId
  if (!nodeId && !edgeId) return []
  return activity.events.filter((event) => (
    (nodeId && (event.source_id === nodeId || event.target_id === nodeId))
    || (edgeId && event.edge_id === edgeId)
  )).slice(-8).reverse()
})
const phaseLabel = computed(() => {
  const cursorEvent = activity.visibleEvents.at(-1)
  const phase = activity.isFollowingLive ? topology.currentPhase : cursorEvent?.phase ?? topology.currentPhase
  const round = activity.isFollowingLive ? topology.currentRound : cursorEvent?.round ?? topology.currentRound
  return `${phase} · Round ${round}`
})
const totalPopulationCount = computed(() => (
  topology.populationNetwork?.node_count || topology.selectedNodes.length
))

function describeEvent(event: typeof activity.events[number]) {
  if (event.kind === 'dialogue') {
    return String(event.payload.argument ?? event.payload.participant_name ?? '発言')
  }
  if (event.kind === 'stance_shift') {
    return `${event.payload.before_stance ?? '?'} → ${event.payload.after_stance ?? '?'}`
  }
  if (event.kind === 'relationship_changed') {
    return `関係 ${event.payload.before_strength ?? '?'} → ${event.payload.after_strength ?? '?'}`
  }
  if (event.kind === 'influence') return `影響 ${event.payload.opinion_delta ?? ''}`
  if (event.kind === 'node_status') {
    const count = Number(event.payload.grouped_count ?? 1)
    return count > 1
      ? `${count}人 ${event.payload.status ?? '更新'}`
      : String(event.payload.status ?? '更新')
  }
  return String(event.payload.status ?? event.payload.phase ?? event.kind)
}

function selectTimelineEvent(event: typeof activity.events[number]) {
  activity.selectEvent(event.id)
  focusGraphActivityEvent(event)
}

function selectNode(nodeId: string) {
  view.selectNode(nodeId)
}

function selectEdge(edgeId: string) {
  view.selectEdge(edgeId)
}

function handleMobileChange(event: MediaQueryListEvent) {
  isMobile.value = event.matches
}

onMounted(async () => {
  mobileQuery = window.matchMedia?.('(max-width: 760px)') ?? null
  isMobile.value = mobileQuery?.matches ?? false
  mobileQuery?.addEventListener('change', handleMobileChange)
  if (!props.autoBootstrap || props.mode === 'live') return
  loading.value = true
  bootstrapAbort = new AbortController()
  try {
    await bootstrapGraphActivity(props.simulationId, { signal: bootstrapAbort.signal })
  } catch (cause) {
    if ((cause as { name?: string }).name !== 'AbortError') {
      error.value = 'グラフ履歴を読み込めませんでした'
    }
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  bootstrapAbort?.abort()
  mobileQuery?.removeEventListener('change', handleMobileChange)
  mobileQuery = null
  if (topology.simulationId === props.simulationId) topology.reset()
  if (activity.simulationId === props.simulationId) activity.reset()
  view.reset()
})
</script>

<template>
  <section class="social-graph-workspace live-society-graph" :data-mode="mode">
    <header class="workspace-header">
      <div class="phase-block">
        <span class="eyebrow">Social pulse</span>
        <strong data-testid="phase-label">{{ phaseLabel }}</strong>
      </div>
      <div class="live-state" :class="{ detached: !activity.isFollowingLive }">
        <span class="status-dot" />
        {{ activity.isFollowingLive ? 'Live' : 'Replay' }}
      </div>
      <dl class="workspace-stats">
        <div><dt>活動中</dt><dd>{{ topology.activeNodeCount }}</dd></div>
        <div><dt>変化</dt><dd>{{ activity.changedCount }}</dd></div>
        <div><dt>代表</dt><dd>{{ topology.selectedNodes.length }}</dd></div>
      </dl>
      <label class="agent-search">
        <span>エージェント検索</span>
        <input
          v-model="view.searchQuery"
          type="search"
          placeholder="職業・地域・立場"
          aria-label="エージェント検索"
        >
      </label>
    </header>

    <div class="workspace-main">
      <div class="graph-stage">
        <div class="graph-context" data-testid="graph-context">
          <div>
            <strong>社会ネットワーク</strong>
            <span>検索またはノード選択で詳しく確認</span>
          </div>
          <span class="graph-context-counts">
            代表 {{ topology.selectedNodes.length.toLocaleString() }}人
            <i aria-hidden="true">/</i>
            全体 {{ totalPopulationCount.toLocaleString() }}人
          </span>
        </div>
        <SigmaSocialGraph
          v-if="topology.selectedNodes.length"
          :nodes="displayNodes"
          :edges="visibleEdges"
          :population-network="displayPopulationNetwork"
          :selected-node-id="view.selectedNodeId"
          :selected-edge-id="view.selectedEdgeId"
          :active-event="activeEvent"
          @select-node="selectNode"
          @select-edge="selectEdge"
          @background-click="view.selectNode(null); view.selectEdge(null)"
        />
        <slot
          v-else-if="slots['legacy-fallback']"
          name="legacy-fallback"
        />
        <div v-if="loading" class="graph-message">グラフを同期中…</div>
        <div v-else-if="error" class="graph-message error">{{ error }}</div>
        <div v-else-if="!topology.selectedNodes.length && !slots['legacy-fallback']" class="graph-message">
          社会グラフの到着を待っています
        </div>
        <div class="visual-legend" aria-label="グラフ表現の凡例">
          <span>● 市民代表</span><span>■ 専門家</span><span>発光 = 活動度</span>
        </div>
      </div>

      <aside class="workspace-inspector" aria-label="グラフ詳細">
        <section v-if="selectedNode" data-testid="node-inspector">
          <span class="eyebrow">Agent</span>
          <h3>{{ selectedNode.demographics?.occupation || selectedNode.id }}</h3>
          <p class="stance-chip">{{ selectedNode.stance || '未確定' }}</p>
          <dl class="detail-list">
            <div><dt>地域</dt><dd>{{ selectedNode.demographics?.region || '—' }}</dd></div>
            <div><dt>年齢</dt><dd>{{ selectedNode.demographics?.age || '—' }}</dd></div>
            <div><dt>確信度</dt><dd>{{ Math.round(selectedNode.confidence * 100) }}%</dd></div>
            <div><dt>状態</dt><dd>{{ selectedNode.status }}</dd></div>
          </dl>
          <p v-if="selectedNode.reason" class="agent-reason">{{ selectedNode.reason }}</p>
        </section>
        <section v-else-if="selectedEdge">
          <span class="eyebrow">Relationship</span>
          <h3>{{ selectedEdge.relation_type }}</h3>
          <dl class="detail-list">
            <div><dt>接続</dt><dd>{{ selectedEdge.source }} → {{ selectedEdge.target }}</dd></div>
            <div><dt>強度</dt><dd>{{ selectedEdge.strength.toFixed(2) }}</dd></div>
          </dl>
        </section>
        <section v-else class="inspector-empty">
          <span class="eyebrow">Inspector</span>
          <h3>人物または関係を選択</h3>
          <p>最近の活動、立場、接続先と影響履歴を確認できます。</p>
        </section>

        <section v-if="recentSelectedActivity.length" class="recent-activity">
          <h4>最近の活動</h4>
          <button
            v-for="event in recentSelectedActivity"
            :key="event.id"
            type="button"
            @click="selectTimelineEvent(event)"
          >
            <span>{{ event.kind }}</span>
            {{ describeEvent(event) }}
          </button>
        </section>
      </aside>
    </div>

    <footer class="activity-timeline" data-testid="activity-timeline">
      <div class="timeline-heading">
        <span>Activity timeline</span>
        <button
          v-if="!activity.isFollowingLive"
          data-testid="return-live"
          type="button"
          @click="activity.returnToLive()"
        >
          末尾へ戻る
        </button>
      </div>
      <div class="timeline-track" role="list" aria-label="グラフ活動履歴">
        <button
          v-for="event in timelineEvents"
          :key="event.id"
          type="button"
          role="listitem"
          :data-event-id="event.id"
          :class="['timeline-event', `kind-${event.kind}`, { selected: activity.selectedEventId === event.id }]"
          @click="selectTimelineEvent(event)"
        >
          <span class="timeline-time">R{{ event.round }}</span>
          <strong>{{ event.kind }}</strong>
          <span>{{ describeEvent(event) }}</span>
        </button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.social-graph-workspace {
  --panel: rgba(9, 17, 31, 0.88);
  display: grid;
  grid-template-rows: auto minmax(24rem, 1fr) auto;
  height: 100%;
  min-height: 38rem;
  overflow: hidden;
  color: #e8eef8;
  background:
    radial-gradient(circle at 32% 22%, rgba(42, 93, 137, 0.2), transparent 34%),
    linear-gradient(145deg, #07101d, #0b1524 52%, #070e19);
}

.workspace-header {
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(11rem, 1fr) auto auto minmax(13rem, 22rem);
  align-items: center;
  gap: 1rem;
  padding: 0.8rem 1rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(7, 14, 25, 0.82);
  backdrop-filter: blur(18px);
}

.phase-block { display: grid; gap: 0.15rem; }
.eyebrow { color: #7690ad; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.13em; text-transform: uppercase; }
.live-state { display: flex; align-items: center; gap: 0.4rem; color: #6ee7b7; font-size: 0.78rem; font-weight: 700; text-transform: uppercase; }
.live-state.detached { color: #fbbf24; }
.status-dot { width: 0.48rem; height: 0.48rem; border-radius: 50%; background: currentColor; box-shadow: 0 0 0.75rem currentColor; }

.workspace-stats { display: flex; gap: 0.8rem; margin: 0; }
.workspace-stats div { display: grid; grid-template-columns: auto auto; gap: 0.35rem; align-items: baseline; }
.workspace-stats dt { color: #7990aa; font-size: 0.66rem; }
.workspace-stats dd { margin: 0; font-variant-numeric: tabular-nums; font-weight: 700; }

.agent-search { display: grid; gap: 0.2rem; }
.agent-search span { color: #7990aa; font-size: 0.62rem; }
.agent-search input { width: 100%; border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 0.5rem; outline: none; background: rgba(15, 27, 44, 0.86); color: inherit; padding: 0.55rem 0.65rem; }
.agent-search input:focus-visible { border-color: #67e8f9; box-shadow: 0 0 0 2px rgba(103, 232, 249, 0.2); }

.workspace-main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(17rem, 22rem); min-height: 0; }
.graph-stage { position: relative; min-height: 24rem; overflow: hidden; }
.graph-stage::after { position: absolute; inset: 0; pointer-events: none; content: ''; background: radial-gradient(circle, transparent 45%, rgba(4, 9, 17, 0.55) 100%); }
.graph-context { position: absolute; z-index: 3; top: 0.85rem; right: 0.9rem; left: 0.9rem; display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; pointer-events: none; }
.graph-context > div { display: grid; gap: 0.16rem; }
.graph-context strong { color: #e8eef8; font-size: 0.78rem; letter-spacing: 0.02em; }
.graph-context span { color: #9fb2c9; font-size: 0.66rem; }
.graph-context-counts { display: flex; gap: 0.4rem; align-items: center; border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 99px; background: rgba(7, 14, 25, 0.78); padding: 0.32rem 0.58rem; color: #cbd8e8 !important; font-variant-numeric: tabular-nums; backdrop-filter: blur(10px); }
.graph-context-counts i { color: #60758e; font-style: normal; }
.graph-message { position: absolute; z-index: 3; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #94a3b8; }
.graph-message.error { color: #fb7185; }
.visual-legend { position: absolute; z-index: 3; left: 1rem; bottom: 0.8rem; display: flex; gap: 0.75rem; color: #8fa3bb; font-size: 0.66rem; }

.workspace-inspector { overflow: auto; border-left: 1px solid rgba(148, 163, 184, 0.14); background: var(--panel); padding: 1rem; backdrop-filter: blur(18px); }
.workspace-inspector h3 { margin: 0.35rem 0 0.65rem; font-size: 1.05rem; }
.stance-chip { display: inline-flex; margin: 0 0 0.8rem; border: 1px solid rgba(103, 232, 249, 0.25); border-radius: 99px; color: #a5f3fc; background: rgba(14, 116, 144, 0.16); padding: 0.25rem 0.55rem; font-size: 0.7rem; }
.detail-list { display: grid; gap: 0.5rem; margin: 0; }
.detail-list div { display: flex; justify-content: space-between; gap: 0.8rem; border-bottom: 1px solid rgba(148, 163, 184, 0.08); padding-bottom: 0.45rem; }
.detail-list dt { color: #7890aa; font-size: 0.7rem; }
.detail-list dd { margin: 0; max-width: 70%; text-align: right; font-size: 0.75rem; }
.agent-reason, .inspector-empty p { color: #9fb0c4; font-size: 0.78rem; line-height: 1.6; }
.recent-activity { margin-top: 1.2rem; }
.recent-activity h4 { color: #8197af; font-size: 0.72rem; }
.recent-activity button { display: grid; width: 100%; margin-bottom: 0.4rem; border: 1px solid rgba(148, 163, 184, 0.1); border-radius: 0.45rem; text-align: left; background: rgba(20, 35, 54, 0.6); color: #dce6f2; padding: 0.5rem; font-size: 0.7rem; cursor: pointer; }
.recent-activity button span { color: #67e8f9; font-size: 0.6rem; text-transform: uppercase; }

.activity-timeline { min-width: 0; border-top: 1px solid rgba(148, 163, 184, 0.14); background: rgba(7, 14, 25, 0.92); padding: 0.65rem 0.8rem; }
.timeline-heading { display: flex; justify-content: space-between; color: #8197af; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.timeline-heading button { border: 0; background: transparent; color: #67e8f9; cursor: pointer; }
.timeline-track { display: flex; gap: 0.45rem; overflow-x: auto; padding-top: 0.5rem; scrollbar-width: thin; }
.timeline-event { display: grid; flex: 0 0 11rem; min-height: 3.4rem; border: 1px solid rgba(148, 163, 184, 0.12); border-radius: 0.45rem; text-align: left; background: rgba(15, 27, 44, 0.72); color: #aebdd0; padding: 0.45rem 0.55rem; font-size: 0.64rem; cursor: pointer; }
.timeline-event strong { color: #e5edf7; font-size: 0.68rem; }
.timeline-event.selected { border-color: #67e8f9; box-shadow: inset 0 0 1rem rgba(103, 232, 249, 0.08); }
.timeline-time { color: #6f87a2; }

@media (max-width: 760px) {
  .workspace-header { grid-template-columns: 1fr auto; }
  .workspace-stats { order: 3; }
  .agent-search { grid-column: 1 / -1; }
  .workspace-main { grid-template-columns: 1fr; }
  .graph-stage { min-height: 19rem; }
  .graph-context { align-items: flex-end; flex-direction: column-reverse; }
  .workspace-inspector { max-height: 15rem; border-top: 1px solid rgba(148, 163, 184, 0.14); border-left: 0; }
  .visual-legend { flex-wrap: wrap; }
}

@media (prefers-reduced-motion: reduce) {
  .status-dot { box-shadow: none; }
  *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; }
}
</style>
