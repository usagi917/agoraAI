<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

interface Node2D {
  id: string
  label: string
  type: string
  importance_score: number
  activity_score: number
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
}

interface EdgeProp {
  source: string
  target: string
  relation_type: string
  weight: number
  label?: string
}

const props = defineProps<{
  nodes: NodeProp[]
  edges: EdgeProp[]
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
  unknown: '#90A4AE',
}

const WIDTH = 800
const HEIGHT = 600

const simNodes = ref<Node2D[]>([])
const simEdges = ref<EdgeProp[]>([])

let animFrame: number | null = null

function nodeColor(type: string) {
  return TYPE_COLORS[type] ?? TYPE_COLORS.unknown
}

function nodeRadius(importance: number) {
  return 4 + importance * 8
}

function initSimulation() {
  simNodes.value = props.nodes.map((n, i) => ({
    ...n,
    x: WIDTH / 2 + (Math.cos(i * 2.4) * 100),
    y: HEIGHT / 2 + (Math.sin(i * 2.4) * 100),
    vx: 0,
    vy: 0,
  }))
  simEdges.value = [...props.edges]
}

function tick() {
  const nodes = simNodes.value
  const edges = simEdges.value
  const alpha = 0.3

  // Repulsion
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      let dx = nodes[j].x - nodes[i].x
      let dy = nodes[j].y - nodes[i].y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = -200 / (dist * dist) * alpha
      const fx = force * dx / dist
      const fy = force * dy / dist
      nodes[i].vx -= fx
      nodes[i].vy -= fy
      nodes[j].vx += fx
      nodes[j].vy += fy
    }
  }

  // Attraction (edges)
  const nodeMap = new Map(nodes.map(n => [n.id, n]))
  for (const edge of edges) {
    const s = nodeMap.get(edge.source)
    const t = nodeMap.get(edge.target)
    if (!s || !t) continue
    const dx = t.x - s.x
    const dy = t.y - s.y
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const force = (dist - 80) * 0.01 * alpha
    const fx = force * dx / dist
    const fy = force * dy / dist
    s.vx += fx
    s.vy += fy
    t.vx -= fx
    t.vy -= fy
  }

  // Centering
  for (const n of nodes) {
    n.vx += (WIDTH / 2 - n.x) * 0.002
    n.vy += (HEIGHT / 2 - n.y) * 0.002
  }

  // Apply velocity with damping
  for (const n of nodes) {
    n.vx *= 0.85
    n.vy *= 0.85
    n.x += n.vx
    n.y += n.vy
    // Bounds
    n.x = Math.max(20, Math.min(WIDTH - 20, n.x))
    n.y = Math.max(20, Math.min(HEIGHT - 20, n.y))
  }

  // Trigger reactivity
  simNodes.value = [...nodes]
}

function startLoop() {
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
  return simNodes.value.find(n => n.id === edge.source)
}

function getTargetNode(edge: EdgeProp) {
  return simNodes.value.find(n => n.id === edge.target)
}

watch(() => [props.nodes, props.edges], () => {
  stopLoop()
  initSimulation()
  startLoop()
}, { deep: true })

onMounted(() => {
  initSimulation()
  startLoop()
})

onUnmounted(() => {
  stopLoop()
})
</script>

<template>
  <div class="force-graph-2d" data-testid="graph-2d-fallback">
    <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" class="graph-svg">
      <line
        v-for="edge in simEdges"
        :key="`${edge.source}-${edge.target}`"
        :x1="getSourceNode(edge)?.x ?? 0"
        :y1="getSourceNode(edge)?.y ?? 0"
        :x2="getTargetNode(edge)?.x ?? 0"
        :y2="getTargetNode(edge)?.y ?? 0"
        :stroke="nodeColor(edge.relation_type)"
        stroke-opacity="0.4"
        :stroke-width="edge.weight * 2 + 0.5"
      />
      <g v-for="node in simNodes" :key="node.id">
        <circle
          :cx="node.x"
          :cy="node.y"
          :r="nodeRadius(node.importance_score)"
          :fill="nodeColor(node.type)"
          fill-opacity="0.85"
          :stroke="nodeColor(node.type)"
          stroke-opacity="0.4"
          stroke-width="2"
        />
        <text
          :x="node.x"
          :y="node.y + nodeRadius(node.importance_score) + 12"
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
}

.graph-svg {
  width: 100%;
  height: 100%;
  background: radial-gradient(ellipse at 30% 40%, #0d0d2b 0%, #060614 50%, #020208 100%);
  border-radius: var(--radius, 8px);
}

.node-label {
  font-size: 10px;
  fill: rgba(255, 255, 255, 0.7);
  pointer-events: none;
}
</style>
