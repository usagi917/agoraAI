<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import ForceGraph from 'force-graph'
import { forceCollide } from 'd3-force'

import {
  DEFAULT_PHYSICS,
  buildAdjacency,
  clamp01,
  computeDegrees,
  createMergeGraphDataCache,
  labelAlpha,
  linkColor as computeLinkColor,
  linkWidth as computeLinkWidth,
  mergeGraphData,
  nodeColor,
  nodeDisplayColor,
  nodeRadius,
  syntheticLinkColor,
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
const mergeCache = createMergeGraphDataCache()
let didFitOnce = false
const LAYOUT_COOLDOWN_TICKS = 160
const LAYOUT_COOLDOWN_TIME_MS = 5000
const HIGH_DEGREE_LABEL_THRESHOLD = 8
const LARGE_GRAPH_THRESHOLD = 1500
const POPULATION_UNDECIDED_COLOR = '#475569'
const PULSE_DURATION_MS = 900

// Firing "synapse" links, keyed by a STABLE string (not the object reference):
// mergeGraphData rebuilds the link array on every store update, so an object key
// would orphan the entry — dropping the glow early and leaking the map.
const firingLinks = new Map<string, number>()
let reducedMotion = false
let motionQuery: MediaQueryList | null = null

const adjacency = computed(() => buildAdjacency(currentLinks.value))
const degreeByNodeId = computed(() => computeDegrees(currentLinks.value))
const nodeById = computed(() => new Map(currentNodes.value.map((node) => [node.id, node])))
const effectivePhysics = computed<GraphPhysics>(() => ({ ...DEFAULT_PHYSICS, ...props.physics }))
const isLargeGraph = computed(() => currentNodes.value.length > LARGE_GRAPH_THRESHOLD)
const nonPopulationNodeCount = computed(() => currentNodes.value.filter((node) => node.tier !== 'population').length)

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

function endpointNode(end: unknown): SimNode | null {
  if (end && typeof end === 'object' && 'id' in end) return end as SimNode
  const id = endpointId(end)
  return id ? nodeById.value.get(id) ?? null : null
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

function displayLinkColor(link: SimLink): string {
  const dimmed = isLinkDimmed(link)
  if (link.id?.startsWith('pop-edge-')) {
    return withAlpha('#7dd3fc', dimmed ? 0.015 : 0.05)
  }
  if (link.synthetic) {
    const source = endpointNode(link.source)
    const target = endpointNode(link.target)
    return syntheticLinkColor(
      source ? nodeDisplayColor(source) : '#94a3b8',
      target ? nodeDisplayColor(target) : '#94a3b8',
      dimmed,
    )
  }
  const intensity = firingIntensity(link)
  if (intensity > 0 && !dimmed) {
    return withAlpha(nodeColor(link.relation_type), Math.min(0.95, 0.55 + intensity * 0.4))
  }
  return computeLinkColor(link.relation_type, link.weight, dimmed)
}

function displayLinkWidth(link: SimLink): number {
  if (link.id?.startsWith('pop-edge-')) return 0.4
  if (link.synthetic) return isLinkDimmed(link) ? 0.45 : 0.7 + clamp01(link.weight) * 1.05
  const base = computeLinkWidth(link.weight)
  const intensity = firingIntensity(link)
  return intensity > 0 ? base * (1 + intensity * 1.3) : base
}

// Stable identity for a link across mergeGraphData rebuilds: prefer the edge id,
// else the unordered endpoint pair plus relation type (parallel edges differ by type).
function firingKey(link: SimLink): string {
  if (link.id) return link.id
  const s = endpointId(link.source)
  const t = endpointId(link.target)
  return `${[s, t].sort().join('::')}::${link.relation_type}`
}

/**
 * How strongly a link is firing right now, in [0, 1]. Decays linearly over the
 * pulse window; expired entries are dropped lazily on read. Under reduced motion
 * it collapses to a flat 1 (a static highlight instead of an easing fade).
 */
function firingIntensity(link: SimLink, now: number = performance.now()): number {
  const key = firingKey(link)
  const expiry = firingLinks.get(key)
  if (expiry == null) return 0
  const remaining = expiry - now
  if (remaining <= 0) {
    firingLinks.delete(key)
    return 0
  }
  return reducedMotion ? 1 : Math.min(1, remaining / PULSE_DURATION_MS)
}

/** Overlay a shadow-blurred glow on a firing link (linkCanvasObjectMode 'after'). */
function paintLinkGlow(link: SimLink, ctx: CanvasRenderingContext2D, globalScale: number) {
  const intensity = firingIntensity(link)
  if (intensity <= 0) return
  const source = link.source as SimNode
  const target = link.target as SimNode
  if (typeof source?.x !== 'number' || typeof source?.y !== 'number') return
  if (typeof target?.x !== 'number' || typeof target?.y !== 'number') return

  const color = nodeColor(link.relation_type)
  const curvature = link.curvature ?? (clamp01(link.weight) > 0.7 ? 0.05 : 0.015)
  const dx = target.x - source.x
  const dy = target.y - source.y
  const len = Math.hypot(dx, dy) || 1
  // Match force-graph's curved-link control point so the glow tracks the arc.
  const cx = (source.x + target.x) / 2 + (-dy / len) * curvature * len
  const cy = (source.y + target.y) / 2 + (dx / len) * curvature * len

  ctx.save()
  ctx.beginPath()
  ctx.moveTo(source.x, source.y)
  ctx.quadraticCurveTo(cx, cy, target.x, target.y)
  ctx.strokeStyle = withAlpha(color, 0.35 * intensity)
  ctx.lineWidth = (computeLinkWidth(link.weight) + 2.5 * intensity) / globalScale
  ctx.shadowBlur = 14 * intensity
  ctx.shadowColor = color
  ctx.stroke()
  ctx.restore()
}

/**
 * Fire a conversation "synapse" between two agents. Finds the real (non-synthetic)
 * link joining them in either direction, marks it firing for PULSE_DURATION_MS, and
 * emits a single travelling particle. Returns false when no such link exists.
 */
function firePulse(sourceId: string, targetId: string): boolean {
  const now = performance.now()
  // Sweep expired entries so the map stays bounded even for pairs whose glow is
  // never revisited by the render loop.
  for (const [key, expiry] of firingLinks) {
    if (expiry <= now) firingLinks.delete(key)
  }
  const link = currentLinks.value.find((l) => {
    if (l.synthetic) return false
    const s = endpointId(l.source)
    const t = endpointId(l.target)
    return (s === sourceId && t === targetId) || (s === targetId && t === sourceId)
  })
  if (!link) return false
  firingLinks.set(firingKey(link), now + PULSE_DURATION_MS)
  // No explicit redraw: directional particles keep force-graph's render loop
  // running, so a d3ReheatSimulation() here would only jitter the layout and
  // burn CPU on every incoming utterance.
  if (!reducedMotion && graph) {
    (graph as unknown as { emitParticle: (l: SimLink) => void }).emitParticle(link)
  }
  return true
}

defineExpose({ firePulse })

function handleMotionPreferenceChange(event: MediaQueryListEvent) {
  reducedMotion = event.matches
}

function createGraph(element: HTMLElement) {
  // force-graph default export is a class in TS but is also callable.
  // Use `new` for a clean typed constructor path.
  const FG = ForceGraph as unknown as new (el: HTMLElement) => InstanceType<typeof ForceGraph>
  return new FG(element)
}

function paintNode(node: SimNode, ctx: CanvasRenderingContext2D, globalScale: number) {
  if (typeof node.x !== 'number' || typeof node.y !== 'number') return

  if (node.tier === 'population') {
    const popDimmed = isNodeDimmed(node.id)
    const color = node.stance ? nodeDisplayColor(node) : POPULATION_UNDECIDED_COLOR
    ctx.beginPath()
    ctx.arc(node.x, node.y, nodeRadius(node), 0, Math.PI * 2)
    ctx.fillStyle = withAlpha(color, popDimmed ? 0.08 : node.stance ? 0.75 : 0.45)
    ctx.fill()
    return
  }

  const degree = degreeByNodeId.value.get(node.id) ?? 0
  const r = nodeRadius(node, degree)
  const baseColor = nodeDisplayColor(node)
  const dimmed = isNodeDimmed(node.id)
  const selected = props.selectedNodeId === node.id
  const hovered = hoveredNodeId.value === node.id
  const active = node.status === 'speaking' || node.status === 'activating'
  const alpha = dimmed ? 0.15 : selected ? 1 : 0.92

  if (!dimmed) {
    const glowRadius = r * 2.4
    const halo = ctx.createRadialGradient(node.x, node.y, r * 0.3, node.x, node.y, glowRadius)
    halo.addColorStop(0, withAlpha(baseColor, selected || hovered || active ? 0.45 : 0.22))
    ctx.beginPath()
    halo.addColorStop(1, withAlpha(baseColor, 0))
    ctx.arc(node.x, node.y, glowRadius, 0, Math.PI * 2)
    ctx.fillStyle = halo
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

  if (active && !dimmed) {
    // Speaking nodes "breathe": a sine-driven ring that swells and fades. Reduced
    // motion pins the phase so the ring is present but static. The directional
    // particle loop keeps repainting, so this time-based value stays animated.
    const phase = reducedMotion ? 1 : (Math.sin(performance.now() / 320) + 1) / 2
    ctx.beginPath()
    ctx.arc(node.x, node.y, r + 5 + phase * 5, 0, Math.PI * 2)
    ctx.strokeStyle = withAlpha(baseColor, 0.28 + phase * 0.34)
    ctx.lineWidth = (0.8 + phase * 0.8) / globalScale
    ctx.stroke()
  }

  const forceLabel = selected || hovered || degree >= HIGH_DEGREE_LABEL_THRESHOLD || nonPopulationNodeCount.value <= 40
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
  ctx.arc(node.x, node.y, nodeRadius(node, degreeByNodeId.value.get(node.id) ?? 0) + 2, 0, Math.PI * 2)
  ctx.fill()
}

function configureForces(g: ReturnType<typeof createGraph>) {
  const p = effectivePhysics.value

  // Adjust the default forces force-graph already wires up.
  const charge = g.d3Force('charge') as { strength?: (v: number) => unknown; distanceMax?: (v: number) => unknown } | undefined
  charge?.strength?.(p.chargeStrength)
  charge?.distanceMax?.(420)

  const link = g.d3Force('link') as
    | {
      distance?: (fn: (l: SimLink) => number) => unknown
      strength?: (fn: (l: SimLink) => number) => unknown
      iterations?: (v: number) => unknown
    }
    | undefined
  link?.distance?.((l: SimLink) => p.linkDistance + (1 - clamp01(l.weight)) * 80)
  link?.strength?.((l: SimLink) => 0.3 + clamp01(l.weight) * 0.5)
  link?.iterations?.(2)

  const center = g.d3Force('center') as { strength?: (v: number) => unknown } | undefined
  center?.strength?.(p.centerStrength)

  const collideIterations = isLargeGraph.value ? 1 : 2
  g.d3Force('collide', forceCollide<SimNode>(
    (node) => node.tier === 'population'
      ? nodeRadius(node)
      : nodeRadius(node, degreeByNodeId.value.get(node.id) ?? 0) + p.collidePadding,
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
  const merged = mergeGraphData(currentNodes.value, props.nodes, props.edges, mergeCache)
  currentNodes.value = merged.nodes
  currentLinks.value = merged.links
  graph.graphData({ nodes: merged.nodes, links: merged.links })
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

  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    reducedMotion = motionQuery.matches
    motionQuery.addEventListener?.('change', handleMotionPreferenceChange)
  }

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
    .linkColor(((l: SimLink) => displayLinkColor(l)) as never)
    .linkWidth(((l: SimLink) => displayLinkWidth(l)) as never)
    .linkCurvature(((l: SimLink) => l.curvature ?? (l.synthetic ? 0.025 : clamp01(l.weight) > 0.7 ? 0.05 : 0.015)) as never)
    .linkDirectionalParticles(((l: SimLink) => (l.synthetic || l.id?.startsWith('pop-edge-') ? 0 : clamp01(l.weight) > 0.75 ? 1 : 0)) as never)
    .linkDirectionalParticleWidth(1.6)
    .linkDirectionalParticleColor(((l: SimLink) => withAlpha(nodeColor(l.relation_type), 0.7)) as never)
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
      if (link.synthetic) return
      const ep = toEdgeProp(link)
      if (ep) emit('select-edge', ep)
    })
    .onLinkHover((link: SimLink | null) => {
      if (link?.synthetic) {
        emit('hover-edge', null)
        refreshCanvas()
        return
      }
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

  // linkCanvasObject(Mode) resolve to any-degrading overloads in this version's
  // force-graph typings, so apply them via a narrow structural cast to keep the
  // rest of the chain type-checked. Only firing links get the extra canvas pass.
  const glowLayer = graph as unknown as {
    linkCanvasObjectMode: (accessor: (l: SimLink) => 'after' | undefined) => unknown
    linkCanvasObject: (renderFn: (l: SimLink, ctx: CanvasRenderingContext2D, scale: number) => void) => unknown
  }
  glowLayer.linkCanvasObjectMode((l) => (firingIntensity(l) > 0 && !reducedMotion ? 'after' : undefined))
  glowLayer.linkCanvasObject((l, ctx, scale) => paintLinkGlow(l, ctx, scale))

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
  motionQuery?.removeEventListener?.('change', handleMotionPreferenceChange)
  motionQuery = null
  firingLinks.clear()
  if (graph) {
    ;(graph as unknown as { _destructor: () => void })._destructor()
    graph = null
  }
})

watch(
  () => [props.nodes.length, props.edges.length, props.nodes, props.edges] as const,
  () => {
    applyData()
    didFitOnce = false
    refreshCanvas()
  },
)

watch(
  () => props.selectedNodeId,
  (id) => {
    if (!graph) return
    if (!id) {
      refreshCanvas()
      return
    }
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
