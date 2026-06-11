<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import ForceGraph from 'force-graph'
import { forceCollide } from 'd3-force'

import {
  DEFAULT_PHYSICS,
  buildAdjacency,
  clamp01,
  computeDegrees,
  labelAlpha,
  linkColor as computeLinkColor,
  linkWidth as computeLinkWidth,
  mergeGraphData,
  nodeColor,
  nodeDisplayColor,
  nodeRadius,
  toEdgeProp,
  toNodeProp,
  withAlpha,
  type EdgeProp,
  type GraphPhysics,
  type NodeProp,
  type SimLink,
  type SimNode,
} from './forceGraphHelpers'

const props = withDefaults(defineProps<{
  nodes: NodeProp[]
  edges: EdgeProp[]
  selectedNodeId?: string | null
  highlightedNodeIds?: string[]
  physics?: Partial<GraphPhysics>
}>(), {
  selectedNodeId: null,
  highlightedNodeIds: () => [],
  physics: () => ({}),
})

const emit = defineEmits<{
  (e: 'select-node', node: NodeProp): void
  (e: 'select-edge', edge: EdgeProp): void
  (e: 'hover-edge', edge: EdgeProp | null): void
  (e: 'background-click'): void
}>()

const host = ref<HTMLElement | null>(null)
const hoveredNodeId = ref<string | null>(null)

let graph: ReturnType<typeof createGraph> | null = null
let resizeObserver: ResizeObserver | null = null
const currentNodes = ref<SimNode[]>([])
const currentLinks = ref<SimLink[]>([])
let didFitOnce = false
const LAYOUT_COOLDOWN_TICKS = 160
const LAYOUT_COOLDOWN_TIME_MS = 5000

const adjacency = computed(() => buildAdjacency(currentLinks.value))
const degrees = computed(() => computeDegrees(currentLinks.value))
const effectivePhysics = computed<GraphPhysics>(() => ({ ...DEFAULT_PHYSICS, ...props.physics }))

const highlightedSet = computed(() => {
  if (!props.highlightedNodeIds?.length) return null
  const ids = new Set(props.highlightedNodeIds)
  if (props.selectedNodeId) ids.add(props.selectedNodeId)
  return ids
})

function activeFocusId(): string | null {
  return props.selectedNodeId || hoveredNodeId.value
}

function isNodeDimmed(nodeId: string): boolean {
  if (highlightedSet.value) return !highlightedSet.value.has(nodeId)
  const focus = activeFocusId()
  if (!focus) return false
  if (focus === nodeId) return false
  return !(adjacency.value.get(focus)?.has(nodeId) ?? false)
}

function endpointId(end: unknown): string {
  if (end == null) return ''
  if (typeof end === 'string') return end
  if (typeof end === 'number') return String(end)
  if (typeof end === 'object' && end !== null && 'id' in end) {
    return String((end as { id?: string | number }).id ?? '')
  }
  return ''
}

function isLinkDimmed(link: SimLink): boolean {
  const source = endpointId(link.source)
  const target = endpointId(link.target)
  if (highlightedSet.value) {
    return !highlightedSet.value.has(source) && !highlightedSet.value.has(target)
  }
  const focus = activeFocusId()
  if (!focus) return false
  return source !== focus && target !== focus
}

function createGraph(element: HTMLElement) {
  // force-graph default export is a class in TS but is also callable.
  // Use `new` for a clean typed constructor path.
  const FG = ForceGraph as unknown as new (el: HTMLElement) => InstanceType<typeof ForceGraph>
  return new FG(element)
}

const HIGH_DEGREE_LABEL_THRESHOLD = 8

/** これを超えるノード数では物理・衝突計算を軽量化する（人口レイヤー想定） */
const LARGE_GRAPH_THRESHOLD = 1500

const isLargeGraph = computed(() => currentNodes.value.length > LARGE_GRAPH_THRESHOLD)

/** スタンス未確定の人口ノードの色（感化されるとスタンス色に変わる） */
const POPULATION_UNDECIDED_COLOR = '#475569'

function paintNode(node: SimNode, ctx: CanvasRenderingContext2D, globalScale: number) {
  if (typeof node.x !== 'number' || typeof node.y !== 'number') return

  // 人口レイヤー: グロー/ラベル無しの極小ドットを最小コストで描く
  if (node.tier === 'population') {
    const popDimmed = isNodeDimmed(node.id)
    const color = node.stance ? nodeDisplayColor(node) : POPULATION_UNDECIDED_COLOR
    ctx.beginPath()
    ctx.arc(node.x, node.y, nodeRadius(node), 0, Math.PI * 2)
    ctx.fillStyle = withAlpha(color, popDimmed ? 0.08 : node.stance ? 0.75 : 0.45)
    ctx.fill()
    return
  }

  const degree = degrees.value.get(node.id) ?? 0
  const r = nodeRadius(node, degree)
  const baseColor = nodeDisplayColor(node)
  const dimmed = isNodeDimmed(node.id)
  const selected = props.selectedNodeId === node.id
  const hovered = hoveredNodeId.value === node.id
  const alpha = dimmed ? 0.15 : selected ? 1 : 0.92

  // Obsidian 風の発光ハロー（フォーカス時は強め）
  if (!dimmed) {
    const glowRadius = r * 2.4
    const glow = ctx.createRadialGradient(node.x, node.y, r * 0.3, node.x, node.y, glowRadius)
    glow.addColorStop(0, withAlpha(baseColor, selected || hovered ? 0.45 : 0.22))
    glow.addColorStop(1, withAlpha(baseColor, 0))
    ctx.beginPath()
    ctx.arc(node.x, node.y, glowRadius, 0, Math.PI * 2)
    ctx.fillStyle = glow
    ctx.fill()
  }

  ctx.beginPath()
  ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
  ctx.fillStyle = withAlpha(baseColor, alpha)
  ctx.fill()

  if (selected) {
    ctx.strokeStyle = '#f8fafc'
    ctx.lineWidth = 2.5 / globalScale
    ctx.stroke()
  }

  // ラベル: ズームに応じて連続フェード。選択/ホバー/ハブは常時表示。
  const forceLabel = selected || hovered || degree >= HIGH_DEGREE_LABEL_THRESHOLD
  const fade = forceLabel ? Math.max(labelAlpha(globalScale), 0.95) : labelAlpha(globalScale)
  if (fade > 0.02 && !dimmed) {
    const fontSize = 10 / globalScale
    ctx.font = `${fontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.lineWidth = 3 / globalScale
    ctx.strokeStyle = `rgba(8, 9, 18, ${0.88 * fade})`
    ctx.lineJoin = 'round'
    const labelY = node.y + r + 3
    ctx.strokeText(node.label, node.x, labelY)
    ctx.fillStyle = `rgba(226, 232, 240, ${0.85 * fade})`
    ctx.fillText(node.label, node.x, labelY)
  }
}

function paintNodePointerArea(node: SimNode, color: string, ctx: CanvasRenderingContext2D) {
  if (typeof node.x !== 'number' || typeof node.y !== 'number') return
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(node.x, node.y, nodeRadius(node, degrees.value.get(node.id) ?? 0) + 2, 0, Math.PI * 2)
  ctx.fill()
}

function configureForces(g: ReturnType<typeof createGraph>) {
  const p = effectivePhysics.value

  // Adjust the default forces force-graph already wires up.
  const charge = g.d3Force('charge') as { strength?: (v: number) => unknown; distanceMax?: (v: number) => unknown } | undefined
  charge?.strength?.(p.chargeStrength)
  charge?.distanceMax?.(420)

  const link = g.d3Force('link') as
    | { distance?: (fn: (l: SimLink) => number) => unknown; strength?: (fn: (l: SimLink) => number) => unknown }
    | undefined
  link?.distance?.((l: SimLink) => p.linkDistance + (1 - clamp01(l.weight)) * 80)
  link?.strength?.((l: SimLink) => 0.3 + clamp01(l.weight) * 0.5)

  const center = g.d3Force('center') as { strength?: (v: number) => unknown } | undefined
  center?.strength?.(p.centerStrength)

  // ノード重なり防止（次数ベースの半径 + 余白）。
  // 大規模グラフでは iterations を下げ、人口ドットは余白なしにして計算量を抑える。
  const collideIterations = isLargeGraph.value ? 1 : 2
  g.d3Force('collide', forceCollide<SimNode>(
    (n) => n.tier === 'population'
      ? nodeRadius(n)
      : nodeRadius(n, degrees.value.get(n.id) ?? 0) + p.collidePadding,
  ).iterations(collideIterations))

  g.d3VelocityDecay(isLargeGraph.value ? 0.55 : 0.4)
}

function syncSize() {
  if (!host.value || !graph) return
  const rect = host.value.getBoundingClientRect()
  const w = Math.max(320, Math.round(rect.width || 900))
  const h = Math.max(280, Math.round(rect.height || 620))
  graph.width(w).height(h)
}

let wasLargeGraph = false

function applyData() {
  if (!graph) return
  const merged = mergeGraphData(currentNodes.value, props.nodes, props.edges)
  currentNodes.value = merged.nodes
  currentLinks.value = merged.links
  graph.graphData({ nodes: merged.nodes, links: merged.links })
  // 人口レイヤーの出入りで規模クラスが変わったら物理設定を引き直す
  if (isLargeGraph.value !== wasLargeGraph) {
    wasLargeGraph = isLargeGraph.value
    configureForces(graph)
  }
}

function refreshCanvas() {
  // Trigger a redraw without restarting the simulation. d3ReheatSimulation()
  // bumps alpha briefly which also forces a render in idle state.
  graph?.d3ReheatSimulation()
}

onMounted(() => {
  if (!host.value) return
  graph = createGraph(host.value)

  graph
    .nodeId('id')
    .linkSource('source')
    .linkTarget('target')
    .backgroundColor('rgba(8, 9, 18, 1)')
    .nodeRelSize(1)
    .nodeVal(0)
    .nodeCanvasObjectMode(() => 'replace')
    .nodeCanvasObject(paintNode as never)
    .nodePointerAreaPaint(paintNodePointerArea as never)
    .linkColor(((l: SimLink) => (
      // 人口エッジは1万本規模で重なるため、ごく薄く描いて Obsidian 的な霞にする
      l.id?.startsWith('pop-edge-')
        ? withAlpha('#7dd3fc', isLinkDimmed(l) ? 0.015 : 0.05)
        : computeLinkColor(l.relation_type, l.weight, isLinkDimmed(l))
    )) as never)
    .linkWidth(((l: SimLink) => (
      l.id?.startsWith('pop-edge-') ? 0.4 : computeLinkWidth(l.weight)
    )) as never)
    .linkDirectionalParticles(((l: SimLink) => (
      // 人口エッジ（数万本規模）はパーティクル無し
      l.id?.startsWith('pop-edge-') ? 0 : clamp01(l.weight) > 0.75 ? 1 : 0
    )) as never)
    .linkDirectionalParticleWidth(1.6)
    .linkDirectionalParticleColor(((l: SimLink) => withAlpha(nodeColor(l.relation_type), 0.7)) as never)
    .warmupTicks(0)
    .cooldownTicks(LAYOUT_COOLDOWN_TICKS)
    .cooldownTime(LAYOUT_COOLDOWN_TIME_MS)
    .d3AlphaDecay(0.0228)
    .d3VelocityDecay(0.4)
    .enableNodeDrag(true)
    .enableZoomInteraction(true)
    .enablePanInteraction(true)
    .onNodeHover((node: SimNode | null) => {
      hoveredNodeId.value = node?.id != null ? String(node.id) : null
      refreshCanvas()
    })
    .onNodeClick((node: SimNode, event: MouseEvent) => {
      if (event && event.detail >= 2) {
        // Double click releases the pinned position.
        const sim = node
        sim.fx = undefined
        sim.fy = undefined
        graph?.d3ReheatSimulation()
        return
      }
      const np = toNodeProp(node)
      if (np) emit('select-node', np)
    })
    .onNodeDragEnd((node: SimNode) => {
      const sim = node
      sim.fx = sim.x
      sim.fy = sim.y
      refreshCanvas()
    })
    .onLinkClick((link: SimLink) => {
      const ep = toEdgeProp(link)
      if (ep) emit('select-edge', ep)
    })
    .onLinkHover((link: SimLink | null) => {
      const ep = link ? toEdgeProp(link) : null
      emit('hover-edge', ep)
      refreshCanvas()
    })
    .onBackgroundClick(() => {
      emit('background-click')
    })
    .onEngineStop(() => {
      if (!didFitOnce && currentNodes.value.length > 0) {
        didFitOnce = true
        graph?.zoomToFit(400, 40)
      }
    })

  configureForces(graph)
  syncSize()
  applyData()

  if (typeof ResizeObserver !== 'undefined' && host.value) {
    resizeObserver = new ResizeObserver(() => syncSize())
    resizeObserver.observe(host.value)
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  if (graph) {
    ;(graph as unknown as { _destructor: () => void })._destructor()
    graph = null
  }
})

watch(
  () => [props.nodes, props.edges] as const,
  () => {
    applyData()
    didFitOnce = false
    refreshCanvas()
  },
  { deep: true },
)

watch(
  () => props.selectedNodeId,
  (id) => {
    if (!graph || !id) return
    const target = currentNodes.value.find((n) => n.id === id)
    if (target && typeof target.x === 'number' && typeof target.y === 'number') {
      graph.centerAt(target.x, target.y, 600)
    }
    refreshCanvas()
  },
)

watch(
  () => props.highlightedNodeIds,
  () => refreshCanvas(),
  { deep: true },
)

watch(
  () => props.physics,
  () => {
    if (!graph) return
    configureForces(graph)
    graph.d3ReheatSimulation()
  },
  { deep: true },
)
</script>

<template>
  <div ref="host" class="force-graph-2d" data-testid="graph-2d" />
</template>

<style scoped>
.force-graph-2d {
  width: 100%;
  height: 100%;
  min-height: 300px;
  overflow: hidden;
  border-radius: var(--radius, 8px);
  background:
    radial-gradient(circle at 25% 20%, rgba(59, 130, 246, 0.08), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.025), rgba(255, 255, 255, 0)),
    #080912;
}

.force-graph-2d :deep(canvas) {
  display: block;
  cursor: grab;
}

.force-graph-2d :deep(canvas:active) {
  cursor: grabbing;
}
</style>
