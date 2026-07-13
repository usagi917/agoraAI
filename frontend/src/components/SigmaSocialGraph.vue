<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import Graph from 'graphology'
import type Sigma from 'sigma'

import type { GraphActivityEvent, PopulationNetworkResponse } from '../api/client'
import { STANCE_COLORS } from '../constants/stances'
import type {
  SocialTopologyEdge,
  SocialTopologyNode,
} from '../stores/socialGraphTopologyStore'
import type { GraphEdge, GraphNode } from '../stores/graphStore'
import ForceGraph2D from './ForceGraph2D.vue'

const props = withDefaults(defineProps<{
  nodes: SocialTopologyNode[]
  edges: SocialTopologyEdge[]
  populationNetwork?: PopulationNetworkResponse | null
  selectedNodeId?: string | null
  selectedEdgeId?: string | null
  activeEvent?: GraphActivityEvent | null
}>(), {
  populationNetwork: null,
  selectedNodeId: null,
  selectedEdgeId: null,
  activeEvent: null,
})

const emit = defineEmits<{
  (event: 'select-node', nodeId: string): void
  (event: 'select-edge', edgeId: string): void
  (event: 'background-click'): void
}>()

const host = ref<HTMLElement | null>(null)
const particleCanvas = ref<HTMLCanvasElement | null>(null)
const usingFallback = ref(false)
const graph = new Graph({ multi: true, type: 'undirected' })
let renderer: Sigma | null = null
let rebuildFrame = 0
let particleFrame = 0
let resizeObserver: ResizeObserver | null = null
let reducedMotion = false
let isUnmounted = false
const populationRenderIdByIndex = new Map<number, string>()
const graphAriaLabel = computed(() => {
  const total = props.populationNetwork?.node_count || props.nodes.length
  return `ソーシャルグラフ。代表エージェント${props.nodes.length}人、全体${total}人、関係${props.edges.length}件。ノードを選択すると詳細を確認できます。`
})

const POPULATION_EDGE_CAP = 12000
const POPULATION_CLUSTER_THRESHOLD = 2000
const POPULATION_CLUSTER_COUNT = 320
const POPULATION_CLUSTER_EDGE_CAP = 1800

function hashUnit(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index++) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0) / 4294967295
}

function positionFor(id: string, index: number, population = false) {
  const angle = hashUnit(`${id}:angle`) * Math.PI * 2
  const depth = hashUnit(`${id}:depth`)
  const radius = population
    ? 1.3 + Math.sqrt(depth) * 7.5
    : 0.8 + Math.sqrt(index + 1) * 0.42
  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle) * radius * (0.72 + depth * 0.18),
    depth,
  }
}

function canUseWebGL() {
  if (typeof document === 'undefined') return false
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl'))
  } catch {
    return false
  }
}

function addRepresentativeNodes() {
  props.nodes.forEach((node, index) => {
    const position = positionFor(node.id, index)
    graph.addNode(node.id, {
      x: position.x,
      y: position.y,
      zIndex: Math.round(position.depth * 10) + (node.activity > 0 ? 20 : 0),
      size: 7 + node.confidence * 5 + node.activity * 4,
      color: STANCE_COLORS[node.stance] ?? '#94a3b8',
      label: node.demographics?.occupation || `Agent ${node.agent_index}`,
      forceLabel: props.selectedNodeId === node.id,
      highlighted: node.activity > 0.5 || props.selectedNodeId === node.id,
      type: node.role === 'expert' ? 'square' : 'circle',
      tier: 'representative',
    })
  })
}

function addPopulationLayer() {
  const network = props.populationNetwork
  if (!network) return
  populationRenderIdByIndex.clear()
  for (const node of network.nodes) {
    if (graph.hasNode(node.id)) populationRenderIdByIndex.set(node.agent_index, node.id)
  }

  if (network.nodes.length > POPULATION_CLUSTER_THRESHOLD) {
    const clusterSizes = new Map<number, number>()
    for (const node of network.nodes) {
      if (populationRenderIdByIndex.has(node.agent_index)) continue
      const clusterIndex = node.agent_index % POPULATION_CLUSTER_COUNT
      populationRenderIdByIndex.set(node.agent_index, `population-cluster:${clusterIndex}`)
      clusterSizes.set(clusterIndex, (clusterSizes.get(clusterIndex) ?? 0) + 1)
    }
    for (const [clusterIndex, memberCount] of clusterSizes) {
      const id = `population-cluster:${clusterIndex}`
      const position = positionFor(id, clusterIndex, true)
      graph.addNode(id, {
        x: position.x,
        y: position.y,
        zIndex: Math.round(position.depth * 4),
        size: 1.8 + Math.sqrt(memberCount) * 0.55,
        color: '#6685aa',
        label: '',
        forceLabel: false,
        type: 'circle',
        tier: 'population-cluster',
        memberCount,
      })
    }
    return
  }

  network.nodes.forEach((node, index) => {
    if (graph.hasNode(node.id)) return
    const position = positionFor(node.id, index, true)
    graph.addNode(node.id, {
      x: position.x,
      y: position.y,
      zIndex: Math.round(position.depth * 4),
      size: 1.55,
      color: '#6685aa',
      label: '',
      forceLabel: false,
      type: 'circle',
      tier: 'population',
    })
    populationRenderIdByIndex.set(node.agent_index, node.id)
  })
}

function addEdges() {
  for (const edge of props.edges) {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) continue
    graph.addEdgeWithKey(`social:${edge.id}`, edge.source, edge.target, {
      originalId: edge.id,
      size: Math.max(0.22, 0.18 + edge.strength * 0.58 + edge.activity * 1.8),
      color: edge.activity > 0 ? '#e0f2fe' : '#315777',
      zIndex: edge.activity > 0 ? 10 : 1,
      tier: 'social',
    })
  }

  const network = props.populationNetwork
  if (!network) return
  const populationEdges = network.edges.length > POPULATION_EDGE_CAP
    ? [...network.edges].sort((left, right) => right[2] - left[2]).slice(0, POPULATION_EDGE_CAP)
    : network.edges
  const clustered = network.nodes.length > POPULATION_CLUSTER_THRESHOLD
  const aggregatedEdges = new Map<string, {
    source: string
    target: string
    strength: number
    count: number
  }>()
  populationEdges.forEach(([sourceIndex, targetIndex, strength]) => {
    const source = populationRenderIdByIndex.get(sourceIndex)
    const target = populationRenderIdByIndex.get(targetIndex)
    if (!source || !target || !graph.hasNode(source) || !graph.hasNode(target)) return
    if (source === target) return
    const key = [source, target].sort().join('::')
    const aggregate = aggregatedEdges.get(key)
    if (aggregate) {
      aggregate.strength += strength
      aggregate.count += 1
    } else {
      aggregatedEdges.set(key, { source, target, strength, count: 1 })
    }
  })
  const renderEdges = Array.from(aggregatedEdges.values())
    .sort((left, right) => right.count - left.count)
    .slice(0, clustered ? POPULATION_CLUSTER_EDGE_CAP : POPULATION_EDGE_CAP)
  renderEdges.forEach(({ source, target, strength, count }, index) => {
    graph.addEdgeWithKey(`population:${index}`, source, target, {
      originalId: `population:${index}`,
      size: Math.max(0.15, (strength / count) * 0.35 + Math.log2(count + 1) * 0.08),
      color: '#213f5b',
      zIndex: 0,
      tier: 'population',
    })
  })
}

function rebuildGraph() {
  rebuildFrame = 0
  graph.clear()
  addRepresentativeNodes()
  addPopulationLayer()
  addEdges()
  renderer?.refresh()
}

function scheduleRebuild() {
  if (rebuildFrame) cancelAnimationFrame(rebuildFrame)
  rebuildFrame = requestAnimationFrame(rebuildGraph)
}

function resizeParticleCanvas() {
  const canvas = particleCanvas.value
  const element = host.value
  if (!canvas || !element) return
  const ratio = window.devicePixelRatio || 1
  canvas.width = Math.max(1, Math.floor(element.clientWidth * ratio))
  canvas.height = Math.max(1, Math.floor(element.clientHeight * ratio))
  canvas.style.width = `${element.clientWidth}px`
  canvas.style.height = `${element.clientHeight}px`
}

function animateParticle(event: GraphActivityEvent | null) {
  if (particleFrame) cancelAnimationFrame(particleFrame)
  const canvas = particleCanvas.value
  if (!renderer || !canvas || !event?.source_id || !event.target_id) return
  if (!graph.hasNode(event.source_id) || !graph.hasNode(event.target_id)) return
  resizeParticleCanvas()
  const context = canvas.getContext('2d')
  if (!context) return
  const startedAt = performance.now()
  const duration = reducedMotion ? 1 : 720

  const draw = (now: number) => {
    const ratio = window.devicePixelRatio || 1
    context.clearRect(0, 0, canvas.width, canvas.height)
    const sourceAttributes = graph.getNodeAttributes(event.source_id!)
    const targetAttributes = graph.getNodeAttributes(event.target_id!)
    const source = renderer?.graphToViewport({
      x: Number(sourceAttributes.x),
      y: Number(sourceAttributes.y),
    })
    const target = renderer?.graphToViewport({
      x: Number(targetAttributes.x),
      y: Number(targetAttributes.y),
    })
    if (!source || !target) return
    const progress = reducedMotion ? 0.5 : Math.min(1, (now - startedAt) / duration)
    const x = (source.x + (target.x - source.x) * progress) * ratio
    const y = (source.y + (target.y - source.y) * progress) * ratio
    context.save()
    context.shadowBlur = reducedMotion ? 8 : 18
    context.shadowColor = '#e0f2fe'
    context.fillStyle = '#f8fafc'
    context.beginPath()
    context.arc(x, y, (reducedMotion ? 3 : 2.4) * ratio, 0, Math.PI * 2)
    context.fill()
    context.restore()
    if (!reducedMotion && progress < 1) particleFrame = requestAnimationFrame(draw)
  }
  particleFrame = requestAnimationFrame(draw)
}

const fallbackNodes = computed<GraphNode[]>(() => {
  const representativeIds = new Set(props.nodes.map((node) => node.id))
  const result: GraphNode[] = props.nodes.map((node) => ({
    id: node.id,
    label: node.demographics?.occupation || `Agent ${node.agent_index}`,
    type: 'agent',
    importance_score: node.confidence,
    stance: node.stance,
    activity_score: node.activity,
    sentiment_score: 0,
    status: node.status,
    group: node.stance,
  }))
  const populationNodes = props.populationNetwork?.nodes ?? []
  if (populationNodes.length > POPULATION_CLUSTER_THRESHOLD) {
    const counts = new Map<number, number>()
    for (const node of populationNodes) {
      if (representativeIds.has(node.id)) continue
      const clusterIndex = node.agent_index % POPULATION_CLUSTER_COUNT
      counts.set(clusterIndex, (counts.get(clusterIndex) ?? 0) + 1)
    }
    for (const [clusterIndex, count] of counts) {
      result.push({
        id: `population-cluster:${clusterIndex}`,
        label: '',
        type: 'agent',
        importance_score: Math.min(1, count / 100),
        stance: '',
        activity_score: 0,
        sentiment_score: 0,
        status: 'idle',
        group: 'population',
        tier: 'population',
      })
    }
    return result
  }
  for (const node of populationNodes) {
    if (representativeIds.has(node.id)) continue
    result.push({
      id: node.id,
      label: '',
      type: 'agent',
      importance_score: 0.1,
      stance: '',
      activity_score: 0,
      sentiment_score: 0,
      status: 'idle',
      group: 'population',
      tier: 'population',
    })
  }
  return result
})

const fallbackEdges = computed<GraphEdge[]>(() => {
  const result = props.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    relation_type: edge.relation_type,
    weight: edge.strength,
    direction: 'undirected' as const,
    status: 'active',
  }))
  const network = props.populationNetwork
  if (!network) return result
  const representativeIds = new Set(props.nodes.map((node) => node.id))
  const clustered = network.nodes.length > POPULATION_CLUSTER_THRESHOLD
  const renderIdByIndex = new Map(network.nodes.map((node) => [
    node.agent_index,
    representativeIds.has(node.id)
      ? node.id
      : clustered
        ? `population-cluster:${node.agent_index % POPULATION_CLUSTER_COUNT}`
        : node.id,
  ]))
  const aggregates = new Map<string, { source: string; target: string; strength: number; count: number }>()
  const rawEdges = network.edges.slice(0, POPULATION_EDGE_CAP)
  rawEdges.forEach(([sourceIndex, targetIndex, strength]) => {
    const source = renderIdByIndex.get(sourceIndex)
    const target = renderIdByIndex.get(targetIndex)
    if (!source || !target || source === target) return
    const key = [source, target].sort().join('::')
    const aggregate = aggregates.get(key)
    if (aggregate) {
      aggregate.strength += strength
      aggregate.count += 1
    } else {
      aggregates.set(key, { source, target, strength, count: 1 })
    }
  })
  Array.from(aggregates.values())
    .sort((left, right) => right.count - left.count)
    .slice(0, clustered ? POPULATION_CLUSTER_EDGE_CAP : POPULATION_EDGE_CAP)
    .forEach(({ source, target, strength, count }, index) => {
    result.push({
      id: `population:${index}`,
      source,
      target,
      relation_type: 'acquaintance',
      weight: strength / count,
      direction: 'undirected',
      status: 'active',
    })
    })
  return result
})

watch(
  () => [props.nodes, props.edges, props.populationNetwork, props.selectedNodeId],
  scheduleRebuild,
)
watch(() => props.activeEvent, animateParticle)
watch(() => props.selectedNodeId, (nodeId) => {
  if (!renderer || !nodeId || !graph.hasNode(nodeId)) return
  const node = graph.getNodeAttributes(nodeId)
  renderer.getCamera().animate({ x: node.x, y: node.y, ratio: 0.28 }, { duration: 360 })
})

onMounted(async () => {
  reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  usingFallback.value = !canUseWebGL()
  if (usingFallback.value || !host.value) return
  await nextTick()
  const [{ default: SigmaRenderer }, { NodeSquareProgram }] = await Promise.all([
    import('sigma'),
    import('@sigma/node-square'),
  ])
  if (isUnmounted || !host.value) return
  rebuildGraph()
  renderer = new SigmaRenderer(graph, host.value, {
    enableEdgeEvents: true,
    renderEdgeLabels: false,
    labelRenderedSizeThreshold: 11,
    labelDensity: 0.25,
    labelGridCellSize: 160,
    labelColor: { color: '#c8d4e3' },
    labelSize: 11,
    minCameraRatio: 0.05,
    maxCameraRatio: 3,
    zIndex: true,
    nodeProgramClasses: { square: NodeSquareProgram },
    nodeReducer: (nodeId, data) => ({
      ...data,
      forceLabel: props.selectedNodeId === nodeId || Boolean(data.forceLabel),
      highlighted: props.selectedNodeId === nodeId || Boolean(data.highlighted),
    }),
    edgeReducer: (_edgeKey, data) => ({
      ...data,
      size: data.originalId === props.selectedEdgeId ? Math.max(Number(data.size), 3) : data.size,
      color: data.originalId === props.selectedEdgeId ? '#f8fafc' : data.color,
    }),
  })
  renderer.on('clickNode', ({ node }) => emit('select-node', node))
  renderer.on('clickEdge', ({ edge }) => emit('select-edge', String(graph.getEdgeAttribute(edge, 'originalId'))))
  renderer.on('clickStage', () => emit('background-click'))
  resizeObserver = new ResizeObserver(() => resizeParticleCanvas())
  resizeObserver.observe(host.value)
  resizeParticleCanvas()
})

onUnmounted(() => {
  isUnmounted = true
  if (rebuildFrame) cancelAnimationFrame(rebuildFrame)
  if (particleFrame) cancelAnimationFrame(particleFrame)
  resizeObserver?.disconnect()
  renderer?.kill()
  renderer = null
})

function selectFallbackEdge(edge: { id?: string }) {
  if (edge.id) emit('select-edge', edge.id)
}
</script>

<template>
  <div
    class="sigma-social-graph"
    data-testid="social-graph-surface"
    role="img"
    :aria-label="graphAriaLabel"
  >
    <ForceGraph2D
      v-if="usingFallback"
      :nodes="fallbackNodes"
      :edges="fallbackEdges"
      :selected-node-id="selectedNodeId"
      @select-node="emit('select-node', $event.id)"
      @select-edge="selectFallbackEdge"
      @background-click="emit('background-click')"
    />
    <template v-else>
      <div ref="host" class="sigma-host" />
      <canvas ref="particleCanvas" class="particle-layer" aria-hidden="true" />
    </template>
  </div>
</template>

<style scoped>
.sigma-social-graph,
.sigma-host {
  position: absolute;
  inset: 0;
  min-height: 22rem;
}

.particle-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
</style>
