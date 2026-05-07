<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

interface Node2D {
  id: string
  label: string
  type: string
  importance_score: number
  activity_score: number
  stance?: string
  status?: string
  x: number
  y: number
  vx: number
  vy: number
}

interface NodeProp {
  id: string
  label: string
  type: string
  importance_score: number
  activity_score: number
  stance?: string
  status?: string
}

interface EdgeProp {
  id?: string
  source: string
  target: string
  relation_type: string
  weight: number
  label?: string
}

const props = withDefaults(defineProps<{
  nodes: NodeProp[]
  edges: EdgeProp[]
  selectedNodeId?: string | null
}>(), {
  selectedNodeId: null,
})

const emit = defineEmits<{
  (e: 'select-node', node: NodeProp): void
  (e: 'select-edge', edge: EdgeProp): void
  (e: 'hover-edge', edge: EdgeProp | null): void
}>()

const TYPE_COLORS: Record<string, string> = {
  organization: '#4FC3F7',
  person: '#FFB74D',
  policy: '#81C784',
  market: '#E57373',
  technology: '#BA68C8',
  resource: '#4DB6AC',
  concept: '#64B5F6',
  risk: '#FF8A65',
  opportunity: '#AED581',
  agent: '#FFB74D',
  friend: '#4FC3F7',
  family: '#FFB74D',
  colleague: '#81C784',
  neighbor: '#4DB6AC',
  acquaintance: '#90A4AE',
  mentions: '#BA68C8',
  default: '#90A4AE',
}

const DEFAULT_WIDTH = 900
const DEFAULT_HEIGHT = 620

const host = ref<HTMLElement | null>(null)
const width = ref(DEFAULT_WIDTH)
const height = ref(DEFAULT_HEIGHT)
const simNodes = ref<Node2D[]>([])
const simEdges = ref<EdgeProp[]>([])
const hoveredNodeId = ref<string | null>(null)

let animFrame: number | null = null
let resizeObserver: ResizeObserver | null = null

const connectedNodeIds = computed(() => {
  const activeId = props.selectedNodeId || hoveredNodeId.value
  if (!activeId) return null
  const ids = new Set<string>([activeId])
  for (const edge of simEdges.value) {
    if (edge.source === activeId) ids.add(edge.target)
    if (edge.target === activeId) ids.add(edge.source)
  }
  return ids
})

function nodeColor(type: string) {
  return TYPE_COLORS[type] ?? TYPE_COLORS.default
}

function relationColor(type: string) {
  return TYPE_COLORS[type] ?? TYPE_COLORS.default
}

function nodeRadius(node: Pick<Node2D, 'importance_score' | 'activity_score' | 'status'>) {
  const activityBoost = node.activity_score > 0 || node.status === 'speaking' ? 3 : 0
  return 5 + Math.max(0, Math.min(1, node.importance_score || 0.4)) * 8 + activityBoost
}

function edgeKey(edge: EdgeProp) {
  return edge.id || `${edge.source}-${edge.target}-${edge.relation_type}`
}

function isNodeDimmed(nodeId: string) {
  return connectedNodeIds.value ? !connectedNodeIds.value.has(nodeId) : false
}

function isEdgeDimmed(edge: EdgeProp) {
  const activeId = props.selectedNodeId || hoveredNodeId.value
  return activeId ? edge.source !== activeId && edge.target !== activeId : false
}

function edgeOpacity(edge: EdgeProp) {
  if (isEdgeDimmed(edge)) return 0.14
  return Math.min(0.72, 0.24 + Math.max(0, Math.min(1, edge.weight || 0.4)) * 0.38)
}

function edgeWidth(edge: EdgeProp) {
  return 0.7 + Math.max(0, Math.min(1, edge.weight || 0.4)) * 2.4
}

function updateSize() {
  const rect = host.value?.getBoundingClientRect()
  width.value = Math.max(320, Math.round(rect?.width || DEFAULT_WIDTH))
  height.value = Math.max(280, Math.round(rect?.height || DEFAULT_HEIGHT))
}

function initSimulation() {
  const previous = new Map(simNodes.value.map((node) => [node.id, node]))
  const radius = Math.min(width.value, height.value) * 0.28
  simNodes.value = props.nodes.map((n, i) => {
    const prior = previous.get(n.id)
    return {
      ...n,
      x: prior?.x ?? width.value / 2 + Math.cos(i * 2.399963) * radius,
      y: prior?.y ?? height.value / 2 + Math.sin(i * 2.399963) * radius,
      vx: prior?.vx ?? 0,
      vy: prior?.vy ?? 0,
    }
  })
  simEdges.value = [...props.edges]
}

function tick() {
  const nodes = simNodes.value
  const edges = simEdges.value
  if (nodes.length === 0) return

  const alpha = 0.34
  const nodeMap = new Map(nodes.map((node) => [node.id, node]))

  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i]
      const b = nodes[j]
      let dx = b.x - a.x
      let dy = b.y - a.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const minDistance = nodeRadius(a) + nodeRadius(b) + 28
      const force = dist < minDistance ? 0.018 * (minDistance - dist) : 260 / (dist * dist)
      dx /= dist
      dy /= dist
      a.vx -= force * dx * alpha
      a.vy -= force * dy * alpha
      b.vx += force * dx * alpha
      b.vy += force * dy * alpha
    }
  }

  for (const edge of edges) {
    const source = nodeMap.get(edge.source)
    const target = nodeMap.get(edge.target)
    if (!source || !target) continue
    const dx = target.x - source.x
    const dy = target.y - source.y
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const preferred = 70 + (1 - Math.max(0, Math.min(1, edge.weight || 0.4))) * 80
    const force = (dist - preferred) * 0.012 * alpha
    source.vx += (force * dx) / dist
    source.vy += (force * dy) / dist
    target.vx -= (force * dx) / dist
    target.vy -= (force * dy) / dist
  }

  for (const node of nodes) {
    node.vx += (width.value / 2 - node.x) * 0.002
    node.vy += (height.value / 2 - node.y) * 0.002
    node.vx *= 0.84
    node.vy *= 0.84
    node.x += node.vx
    node.y += node.vy
    const margin = nodeRadius(node) + 8
    node.x = Math.max(margin, Math.min(width.value - margin, node.x))
    node.y = Math.max(margin, Math.min(height.value - margin, node.y))
  }

  simNodes.value = [...nodes]
}

function startLoop() {
  if (animFrame !== null) return
  const loop = () => {
    tick()
    animFrame = requestAnimationFrame(loop)
  }
  animFrame = requestAnimationFrame(loop)
}

function stopLoop() {
  if (animFrame !== null) {
    cancelAnimationFrame(animFrame)
    animFrame = null
  }
}

function getSourceNode(edge: EdgeProp) {
  return simNodes.value.find((node) => node.id === edge.source)
}

function getTargetNode(edge: EdgeProp) {
  return simNodes.value.find((node) => node.id === edge.target)
}

function handleNodeClick(node: Node2D) {
  emit('select-node', node)
}

function handleEdgeClick(edge: EdgeProp) {
  emit('select-edge', edge)
}

watch(() => [props.nodes, props.edges], () => {
  initSimulation()
  startLoop()
}, { deep: true })

onMounted(async () => {
  await nextTick()
  updateSize()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateSize()
      initSimulation()
    })
    if (host.value) resizeObserver.observe(host.value)
  }
  initSimulation()
  startLoop()
})

onUnmounted(() => {
  stopLoop()
  resizeObserver?.disconnect()
})
</script>

<template>
  <div ref="host" class="force-graph-2d" data-testid="graph-2d">
    <svg :viewBox="`0 0 ${width} ${height}`" class="graph-svg" role="img" aria-label="Relationship graph">
      <line
        v-for="edge in simEdges"
        :key="edgeKey(edge)"
        :x1="getSourceNode(edge)?.x ?? 0"
        :y1="getSourceNode(edge)?.y ?? 0"
        :x2="getTargetNode(edge)?.x ?? 0"
        :y2="getTargetNode(edge)?.y ?? 0"
        :stroke="relationColor(edge.relation_type)"
        :stroke-opacity="edgeOpacity(edge)"
        :stroke-width="edgeWidth(edge)"
        class="edge-line"
        @mouseenter="emit('hover-edge', edge)"
        @mouseleave="emit('hover-edge', null)"
        @click.stop="handleEdgeClick(edge)"
      />
      <g
        v-for="node in simNodes"
        :key="node.id"
        class="node-group"
        :class="{ dimmed: isNodeDimmed(node.id), selected: selectedNodeId === node.id }"
        @mouseenter="hoveredNodeId = node.id"
        @mouseleave="hoveredNodeId = null"
        @click.stop="handleNodeClick(node)"
      >
        <circle
          :cx="node.x"
          :cy="node.y"
          :r="nodeRadius(node)"
          :fill="nodeColor(node.type)"
          :stroke="selectedNodeId === node.id ? '#f8fafc' : nodeColor(node.type)"
          :stroke-width="selectedNodeId === node.id ? 2.5 : 1.5"
        />
        <text
          :x="node.x"
          :y="node.y + nodeRadius(node) + 13"
          text-anchor="middle"
          class="node-label"
        >{{ node.label }}</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.force-graph-2d {
  width: 100%;
  height: 100%;
  min-height: 300px;
  overflow: hidden;
}

.graph-svg {
  width: 100%;
  height: 100%;
  background:
    radial-gradient(circle at 25% 20%, rgba(59, 130, 246, 0.08), transparent 28%),
    linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0)),
    #080912;
  border-radius: var(--radius, 8px);
}

.edge-line {
  cursor: pointer;
  transition: stroke-opacity 0.18s ease, stroke-width 0.18s ease;
}

.edge-line:hover {
  stroke-opacity: 0.9;
}

.node-group {
  cursor: pointer;
  transition: opacity 0.18s ease;
}

.node-group circle {
  fill-opacity: 0.88;
  transition: stroke-width 0.18s ease, fill-opacity 0.18s ease;
}

.node-group:hover circle,
.node-group.selected circle {
  fill-opacity: 1;
}

.node-group.dimmed {
  opacity: 0.24;
}

.node-label {
  font-size: 10px;
  fill: rgba(226, 232, 240, 0.72);
  pointer-events: none;
  paint-order: stroke;
  stroke: rgba(8, 9, 18, 0.88);
  stroke-width: 3px;
  stroke-linejoin: round;
}
</style>
