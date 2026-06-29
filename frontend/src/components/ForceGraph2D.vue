<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import ForceGraph from 'force-graph'

import {
  buildAdjacency,
  clamp01,
  linkColor as computeLinkColor,
  linkWidth as computeLinkWidth,
  mergeGraphData,
  nodeColor,
  nodeDegree,
  nodeDisplayColor,
  nodeRadius,
  toEdgeProp,
  toNodeProp,
  withAlpha,
  type EdgeProp,
  type NodeProp,
  type SimLink,
  type SimNode,
} from './forceGraphHelpers'

const props = withDefaults(defineProps<{
  nodes: NodeProp[]
  edges: EdgeProp[]
  selectedNodeId?: string | null
  highlightedNodeIds?: string[]
}>(), {
  selectedNodeId: null,
  highlightedNodeIds: () => [],
})

const emit = defineEmits<{
  (e: 'select-node', node: NodeProp): void
  (e: 'select-edge', edge: EdgeProp): void
  (e: 'hover-edge', edge: EdgeProp | null): void
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
const MIN_HUB_DEGREE = 3

const adjacency = computed(() => buildAdjacency(currentLinks.value))
const degreeByNodeId = computed(() => {
  const map = new Map<string, number>()
  for (const node of currentNodes.value) {
    map.set(node.id, nodeDegree(node.id, currentLinks.value))
  }
  return map
})

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

function isNodeFocused(nodeId: string): boolean {
  const focus = activeFocusId()
  return focus === nodeId || (focus != null && (adjacency.value.get(focus)?.has(nodeId) ?? false))
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

function paintNode(node: SimNode, ctx: CanvasRenderingContext2D, globalScale: number) {
  if (typeof node.x !== 'number' || typeof node.y !== 'number') return
  const r = nodeRadius(node)
  const baseColor = nodeDisplayColor(node)
  const degree = degreeByNodeId.value.get(node.id) ?? 0
  const hubRatio = Math.min(1, degree / 10)
  const dimmed = isNodeDimmed(node.id)
  const selected = props.selectedNodeId === node.id
  const focused = isNodeFocused(node.id)
  const active = node.status === 'speaking' || node.status === 'activating'
  const alpha = dimmed ? 0.16 : selected ? 1 : focused ? 0.96 : 0.84
  const haloRadius = r + 8 + hubRatio * 14 + (active ? 6 : 0)

  if (!dimmed) {
    const halo = ctx.createRadialGradient(node.x, node.y, r * 0.5, node.x, node.y, haloRadius)
    halo.addColorStop(0, withAlpha(baseColor, selected ? 0.34 : active ? 0.3 : 0.2 + hubRatio * 0.12))
    halo.addColorStop(0.55, withAlpha(baseColor, selected ? 0.14 : 0.08 + hubRatio * 0.08))
    halo.addColorStop(1, withAlpha(baseColor, 0))
    ctx.beginPath()
    ctx.arc(node.x, node.y, haloRadius, 0, Math.PI * 2)
    ctx.fillStyle = halo
    ctx.fill()
  }

  if (degree >= MIN_HUB_DEGREE && !dimmed) {
    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 4 + hubRatio * 4, 0, Math.PI * 2)
    ctx.strokeStyle = withAlpha(baseColor, selected ? 0.72 : 0.34 + hubRatio * 0.18)
    ctx.lineWidth = Math.max(0.8, 1.4 / globalScale)
    ctx.stroke()
  }

  ctx.beginPath()
  ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
  const core = ctx.createRadialGradient(node.x - r * 0.35, node.y - r * 0.4, r * 0.2, node.x, node.y, r)
  core.addColorStop(0, withAlpha('#f8fafc', dimmed ? 0.22 : 0.48))
  core.addColorStop(0.28, withAlpha(baseColor, alpha))
  core.addColorStop(1, withAlpha(baseColor, dimmed ? 0.12 : 0.64))
  ctx.fillStyle = core
  ctx.fill()

  ctx.beginPath()
  ctx.arc(node.x, node.y, r, 0, Math.PI * 2)
  ctx.strokeStyle = selected ? '#f8fafc' : withAlpha(baseColor, dimmed ? 0.12 : 0.56)
  ctx.lineWidth = selected ? 2.5 / globalScale : 1.15 / globalScale
  ctx.stroke()

  if (active && !dimmed) {
    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 7, 0, Math.PI * 2)
    ctx.strokeStyle = withAlpha(baseColor, 0.42)
    ctx.lineWidth = 1 / globalScale
    ctx.stroke()
  }

  if (globalScale > 0.62 && !dimmed && (focused || selected || degree >= MIN_HUB_DEGREE || currentNodes.value.length <= 40)) {
    const fontSize = 10 / globalScale
    ctx.font = `${fontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.lineWidth = 3 / globalScale
    ctx.strokeStyle = 'rgba(8, 9, 18, 0.88)'
    ctx.lineJoin = 'round'
    const labelY = node.y + r + 3
    ctx.strokeText(node.label, node.x, labelY)
    ctx.fillStyle = 'rgba(226, 232, 240, 0.85)'
    ctx.fillText(node.label, node.x, labelY)
  }
}

function paintNodePointerArea(node: SimNode, color: string, ctx: CanvasRenderingContext2D) {
  if (typeof node.x !== 'number' || typeof node.y !== 'number') return
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(node.x, node.y, nodeRadius(node) + 2, 0, Math.PI * 2)
  ctx.fill()
}

function configureForces(g: ReturnType<typeof createGraph>) {
  // Adjust the default forces force-graph already wires up.
  const charge = g.d3Force('charge') as { strength?: (v: number) => unknown; distanceMax?: (v: number) => unknown } | undefined
  charge?.strength?.(-260)
  charge?.distanceMax?.(520)

  const link = g.d3Force('link') as
    | {
      distance?: (fn: (l: SimLink) => number) => unknown
      strength?: (fn: (l: SimLink) => number) => unknown
      iterations?: (v: number) => unknown
    }
    | undefined
  link?.distance?.((l: SimLink) => 44 + (1 - clamp01(l.weight)) * 90)
  link?.strength?.((l: SimLink) => 0.36 + clamp01(l.weight) * 0.58)
  link?.iterations?.(2)

  const center = g.d3Force('center') as { strength?: (v: number) => unknown } | undefined
  center?.strength?.(0.055)
}

function syncSize() {
  if (!host.value || !graph) return
  const rect = host.value.getBoundingClientRect()
  const w = Math.max(320, Math.round(rect.width || 900))
  const h = Math.max(280, Math.round(rect.height || 620))
  graph.width(w).height(h)
}

function applyData() {
  if (!graph) return
  const merged = mergeGraphData(currentNodes.value, props.nodes, props.edges)
  currentNodes.value = merged.nodes
  currentLinks.value = merged.links
  graph.graphData({ nodes: merged.nodes, links: merged.links })
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
    .backgroundColor('rgba(0, 0, 0, 0)')
    .nodeRelSize(1)
    .nodeVal(0)
    .nodeCanvasObjectMode(() => 'replace')
    .nodeCanvasObject(paintNode as never)
    .nodePointerAreaPaint(paintNodePointerArea as never)
    .linkColor(((l: SimLink) => computeLinkColor(l.relation_type, l.weight, isLinkDimmed(l))) as never)
    .linkWidth(((l: SimLink) => computeLinkWidth(l.weight)) as never)
    .linkCurvature(((l: SimLink) => (clamp01(l.weight) > 0.7 ? 0.05 : 0.015)) as never)
    .linkDirectionalParticles(((l: SimLink) => (clamp01(l.weight) > 0.72 ? 3 : clamp01(l.weight) > 0.45 ? 1 : 0)) as never)
    .linkDirectionalParticleWidth(2.2)
    .linkDirectionalParticleColor(((l: SimLink) => withAlpha(nodeColor(l.relation_type), 0.85)) as never)
    .linkDirectionalParticleSpeed(((l: SimLink) => 0.003 + clamp01(l.weight) * 0.006) as never)
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
</script>

<template>
  <div ref="host" class="force-graph-2d" data-testid="graph-2d" />
</template>

<style scoped>
.force-graph-2d {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 300px;
  overflow: hidden;
  border-radius: var(--radius, 8px);
  background:
    linear-gradient(rgba(148, 163, 184, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.03) 1px, transparent 1px),
    radial-gradient(ellipse at center, rgba(15, 23, 42, 0.18), rgba(3, 6, 18, 0.72) 68%),
    #080912;
  background-size: 36px 36px, 36px 36px, 100% 100%;
}

.force-graph-2d::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: "";
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.055), transparent 18%),
    linear-gradient(120deg, rgba(255, 183, 77, 0.055), transparent 32%),
    linear-gradient(300deg, rgba(79, 195, 247, 0.045), transparent 34%);
  mix-blend-mode: screen;
}

.force-graph-2d::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: "";
  background:
    linear-gradient(to right, rgba(8, 9, 18, 0.78), transparent 18%, transparent 82%, rgba(8, 9, 18, 0.78)),
    linear-gradient(to bottom, rgba(8, 9, 18, 0.62), transparent 24%, transparent 80%, rgba(8, 9, 18, 0.84));
}

.force-graph-2d :deep(canvas) {
  position: relative;
  z-index: 1;
  display: block;
  cursor: grab;
}

.force-graph-2d :deep(canvas:active) {
  cursor: grabbing;
}
</style>
