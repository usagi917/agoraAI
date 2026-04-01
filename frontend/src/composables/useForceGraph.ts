import { ref, onMounted, onUnmounted, watch, type Ref } from 'vue'
import ForceGraph3D, { type ForceGraph3DInstance } from '3d-force-graph'
import * as THREE from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import type { GraphNode, GraphEdge } from '../stores/graphStore'
import {
  createSwimMotionState,
  sampleSwimMotion,
  type MotionVector,
  type SwimMotionState,
} from './forceGraphMotion'
import { startThinkingAnimation, type ThinkingVisualMode } from './useThinkingParticles'

// Shared geometries (reused across all nodes to reduce GC pressure)
const sharedSphereCore = new THREE.SphereGeometry(1, 24, 24)
const sharedSphereGlow = new THREE.SphereGeometry(1, 16, 16)
const sharedOctaCore = new THREE.OctahedronGeometry(1, 1)
const sharedOctaGlow = new THREE.OctahedronGeometry(1, 0)

// Pulse shader for agent nodes
const PULSE_VERTEX = /* glsl */ `
uniform float u_pulse;
varying vec3 vNormal;
void main() {
  vec3 pos = position * (1.0 + u_pulse * 0.3);
  vNormal = normalMatrix * normal;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
`

const PULSE_FRAGMENT = /* glsl */ `
uniform vec3 u_color;
uniform float u_pulse;
uniform float u_emissiveIntensity;
uniform float u_opacity;
varying vec3 vNormal;
void main() {
  float diffuse = max(dot(vNormal, normalize(vec3(0.3, 0.5, 1.0))), 0.0);
  vec3 base = u_color * (0.3 + 0.7 * diffuse);
  vec3 emissive = u_color * u_emissiveIntensity;
  vec3 pulse = u_color * u_pulse * 2.0;
  gl_FragColor = vec4(base + emissive + pulse, u_opacity);
}
`

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
  metric: '#FFD54F',
  event: '#F48FB1',
  agent: '#FFB74D',
  unknown: '#90A4AE',
}

const STANCE_COLORS: Record<string, string> = {
  '賛成': '#22c55e',
  '条件付き賛成': '#86efac',
  '中立': '#a3a3a3',
  '条件付き反対': '#fca5a5',
  '反対': '#ef4444',
}

export const RELATION_TYPE_STYLES: Record<string, { color: string; width: number; particleColor: string }> = {
  // Knowledge graph
  trust:        { color: '#4FC3F7', width: 1.5, particleColor: '#80D8FF' },
  influence:    { color: '#BA68C8', width: 1.2, particleColor: '#CE93D8' },
  conflict:     { color: '#EF5350', width: 1.0, particleColor: '#FF8A80' },
  // Social graph
  friend:       { color: '#66BB6A', width: 1.8, particleColor: '#A5D6A7' },
  family:       { color: '#FF7043', width: 2.0, particleColor: '#FFAB91' },
  colleague:    { color: '#42A5F5', width: 1.4, particleColor: '#90CAF9' },
  neighbor:     { color: '#FFCA28', width: 1.0, particleColor: '#FFE082' },
  acquaintance: { color: '#78909C', width: 0.7, particleColor: '#B0BEC5' },
  // Agent-Entity links
  mentions:     { color: '#78909C', width: 0.4, particleColor: '#B0BEC5' },
  // Fallback
  default:      { color: '#90A4AE', width: 0.6, particleColor: '#B0BEC5' },
}

const GRAPH_LAYOUT = {
  chargeStrength: -30,
  linkDistance: 25,
  alphaDecay: 0.008,
  velocityDecay: 0.4,
  warmupTicks: 100,
  cooldownTime: 15000,
} as const

const TRANSITION_LAYOUT = {
  ticks: 90,
  attraction: 0.02,
  repulsion: 640,
  centering: 0.003,
  damping: 0.82,
  maxVelocity: 6,
  desiredDistance: 44,
  newNodeScaleFrom: 0.2,
  removedNodeScaleTo: 0.15,
  removedNodeDrift: 0.14,
} as const

const DEFAULT_NODE_OPACITY = 1
const DEFAULT_LINK_OPACITY = 0.85
const LABEL_OPACITY = 0.9
const MIN_NODE_SIZE = 0.0001

interface Position {
  x: number
  y: number
  z: number
}

interface InternalNode extends Position {
  id: string
  label: string
  type: string
  importance_score: number
  activity_score: number
  color: string
  size: number
  opacity: number
  displayX: number
  displayY: number
  displayZ: number
  swimState: SwimMotionState
  __threeObj?: THREE.Object3D
  vx?: number
  vy?: number
  vz?: number
  fx?: number
  fy?: number
  fz?: number
}

interface InternalLink {
  id: string
  source: string | InternalNode
  target: string | InternalNode
  weight: number
  direction: string
  color: string
  opacity: number
  relationType: string
}

export type { InternalLink }

interface TransitionNodeFrame extends Position {
  label: string
  type: string
  importance_score: number
  color: string
  size: number
  opacity: number
}

interface TransitionLinkFrame {
  source: string
  target: string
  weight: number
  direction: string
  color: string
  opacity: number
  relationType: string
}

interface GraphTransitionNode {
  node: InternalNode
  from: TransitionNodeFrame
  to: TransitionNodeFrame
}

interface GraphTransitionLink {
  link: InternalLink
  from: TransitionLinkFrame
  to: TransitionLinkFrame
}

interface GraphTransitionState {
  targetNodes: GraphNode[]
  targetEdges: GraphEdge[]
  nodes: GraphTransitionNode[]
  links: GraphTransitionLink[]
}

interface PositionedNode {
  x?: number
  y?: number
  z?: number
  displayX?: number
  displayY?: number
  displayZ?: number
}

interface LayoutNode extends Position {
  id: string
  vx: number
  vy: number
  vz: number
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function lerp(start: number, end: number, progress: number) {
  return start + (end - start) * progress
}

function lerpColor(fromColor: string, toColor: string, progress: number) {
  const color = new THREE.Color(fromColor)
  color.lerp(new THREE.Color(toColor), progress)
  return `#${color.getHexString()}`
}

function toMotionVector(position: PositionedNode): MotionVector {
  return {
    x: position.x ?? 0,
    y: position.y ?? 0,
    z: position.z ?? 0,
  }
}

function hasPosition(node: PositionedNode | undefined): node is Position {
  return !!node
    && Number.isFinite(node.x)
    && Number.isFinite(node.y)
    && Number.isFinite(node.z)
}

function getRenderedPosition(node: PositionedNode | undefined): Position {
  if (!node) return { x: 0, y: 0, z: 0 }

  const x = Number.isFinite(node.displayX) ? node.displayX : node.x
  const y = Number.isFinite(node.displayY) ? node.displayY : node.y
  const z = Number.isFinite(node.displayZ) ? node.displayZ : node.z

  return {
    x: Number.isFinite(x) ? x! : 0,
    y: Number.isFinite(y) ? y! : 0,
    z: Number.isFinite(z) ? z! : 0,
  }
}

function getNodeVisuals(type: string, importanceScore: number, stance?: string, nodeId?: string) {
  if (type === 'agent' && stance) {
    // Council members (importance_score > 0.8) get larger nodes
    const isCouncil = importanceScore > 0.8
    const baseSize = isCouncil ? 5.0 : 2.5
    const scaleMultiplier = isCouncil ? 5.0 : 3.5
    return {
      color: STANCE_COLORS[stance] || TYPE_COLORS.agent,
      size: baseSize + importanceScore * scaleMultiplier,
    }
  }
  // KG nodes: slightly smaller
  if (nodeId?.startsWith('kg-')) {
    return {
      color: TYPE_COLORS[type] || TYPE_COLORS.unknown,
      size: 2.0 + importanceScore * 3.0,
    }
  }
  return {
    color: TYPE_COLORS[type] || TYPE_COLORS.unknown,
    size: 3 + importanceScore * 4,
  }
}

function getGraphCenterFromNodes(nodes: PositionedNode[]) {
  const positionedNodes = nodes.filter(hasPosition)
  if (!positionedNodes.length) {
    return { x: 0, y: 0, z: 0 }
  }

  const total = positionedNodes.reduce(
    (acc, node) => ({
      x: acc.x + node.x,
      y: acc.y + node.y,
      z: acc.z + node.z,
    }),
    { x: 0, y: 0, z: 0 },
  )

  return {
    x: total.x / positionedNodes.length,
    y: total.y / positionedNodes.length,
    z: total.z / positionedNodes.length,
  }
}

function toGraphNodeMap(nodes: GraphNode[]) {
  return new Map(nodes.map((node) => [node.id, node]))
}

function toGraphEdgeMap(edges: GraphEdge[]) {
  return new Map(edges.map((edge) => [edge.id, edge]))
}

function getLinkColor(
  sourceId: string,
  ...nodeMaps: Array<Map<string, Pick<GraphNode, 'type' | 'stance'> | InternalNode>>
) {
  for (const nodeMap of nodeMaps) {
    const node = nodeMap.get(sourceId)
    if (node) {
      // agent ノード同士のリンクはソースノードの色を使う
      if (node.type === 'agent') {
        return (node as InternalNode).color || TYPE_COLORS.agent
      }
      return TYPE_COLORS[node.type] || TYPE_COLORS.unknown
    }
  }

  return TYPE_COLORS.unknown
}

function getStanceAwareLinkColor(
  sourceId: string,
  targetId: string,
  nodeMap: Map<string, InternalNode | GraphNode>,
): string {
  const sourceNode = nodeMap.get(sourceId) as (InternalNode & { stance?: string }) | undefined
  const targetNode = nodeMap.get(targetId) as (InternalNode & { stance?: string }) | undefined

  if (!sourceNode || !targetNode) return TYPE_COLORS.unknown

  // Only apply stance coloring for agent nodes
  if (sourceNode.type === 'agent' && targetNode.type === 'agent') {
    const srcStance = (sourceNode as any).stance || (sourceNode as any).group
    const tgtStance = (targetNode as any).stance || (targetNode as any).group
    if (srcStance && tgtStance) {
      if (srcStance === tgtStance) {
        return '#22c55e' // Same stance: green
      }
      return '#ef4444' // Different stance: red
    }
  }

  return getLinkColor(sourceId, nodeMap as any)
}

function setFixedPosition(node: InternalNode, position: Position) {
  node.x = position.x
  node.y = position.y
  node.z = position.z
  node.fx = position.x
  node.fy = position.y
  node.fz = position.z
}

function clearFixedPosition(node: InternalNode) {
  node.fx = undefined
  node.fy = undefined
  node.fz = undefined
}

function updateLabelSprite(group: THREE.Group, node: InternalNode, force = false) {
  const sprite = group.getObjectByName('label') as THREE.Sprite | undefined
  if (!sprite) return

  const lastLabel = group.userData.lastLabel as string | undefined
  if (!force && lastLabel === node.label) return

  const canvas = sprite.userData.canvas as HTMLCanvasElement | undefined
  const ctx = sprite.userData.context as CanvasRenderingContext2D | undefined
  const texture = sprite.userData.texture as THREE.CanvasTexture | undefined
  if (!canvas || !ctx || !texture) return

  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.font = 'bold 24px "Space Grotesk", "Noto Sans JP", sans-serif'
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const displayLabel = node.label.length > 20 ? `${node.label.slice(0, 20)}...` : node.label
  ctx.fillText(displayLabel, canvas.width / 2, canvas.height / 2)
  texture.needsUpdate = true
  group.userData.lastLabel = node.label
}

function applyNodeThreeObjectVisuals(node: InternalNode, object?: THREE.Object3D, forceLabel = false) {
  const group = (object || node.__threeObj) as THREE.Group | undefined
  if (!group) return

  const color = new THREE.Color(node.color)
  const opacity = clamp(node.opacity ?? DEFAULT_NODE_OPACITY, 0, 1)
  const size = Math.max(node.size, MIN_NODE_SIZE)

  const core = group.getObjectByName('core') as THREE.Mesh | undefined
  if (core) {
    core.scale.setScalar(size * 0.6)
    if (core.material instanceof THREE.ShaderMaterial) {
      const u = core.material.uniforms
      u.u_color.value.copy(color)
      u.u_emissiveIntensity.value = 0.8 + node.importance_score * 0.6
      u.u_opacity.value = 0.95 * opacity
    } else {
      const material = core.material as THREE.MeshStandardMaterial
      material.color.copy(color)
      material.emissive.copy(color)
      material.emissiveIntensity = 0.8 + node.importance_score * 0.6
      material.opacity = 0.95 * opacity
    }
  }

  const innerGlow = group.getObjectByName('innerGlow') as THREE.Mesh | undefined
  if (innerGlow) {
    innerGlow.scale.setScalar(size * 1.2)
    const material = innerGlow.material as THREE.MeshBasicMaterial
    material.color.copy(color)
    material.opacity = 0.15 * opacity
  }

  const halo = group.getObjectByName('halo') as THREE.Mesh | undefined
  if (halo) {
    halo.scale.setScalar(size * 2.8)
    const material = halo.material as THREE.MeshBasicMaterial
    material.color.copy(color)
    material.opacity = 0.04 * opacity
  }

  const sprite = group.getObjectByName('label') as THREE.Sprite | undefined
  if (sprite) {
    sprite.scale.set(size * 4, size, 1)
    sprite.position.set(0, -(size * 1.5), 0)
    const material = sprite.material as THREE.SpriteMaterial
    material.opacity = LABEL_OPACITY * opacity
    updateLabelSprite(group, node, forceLabel)
  }

  group.visible = opacity > 0.01
}

function updateInternalNode(node: InternalNode, next: GraphNode) {
  node.label = next.label
  node.type = next.type
  node.importance_score = next.importance_score || 0.5
  node.activity_score = next.activity_score || 0
  const visuals = getNodeVisuals(node.type, node.importance_score, next.stance, node.id)
  node.color = visuals.color
  node.size = visuals.size
  node.opacity = DEFAULT_NODE_OPACITY
}

interface ForceGraphOptions {
  nodeExtension?: (node: InternalNode, group: THREE.Group) => void
}

export type { InternalNode }

export function useForceGraph(
  containerRef: Ref<HTMLElement | null>,
  thinkingModeRef?: Ref<ThinkingVisualMode>,
  options?: ForceGraphOptions,
) {
  const graph = ref<ForceGraph3DInstance | null>(null)
  const graphError = ref('')
  let resizeObserver: ResizeObserver | null = null
  let mountedContainer: HTMLElement | null = null
  let activeTransition: GraphTransitionState | null = null
  let sceneRef: THREE.Scene | null = null

  const internalNodes: InternalNode[] = []
  const internalLinks: InternalLink[] = []
  let thinkingCleanup: (() => void) | null = null
  let externalNodeClickCallback: ((nodeId: string) => void) | null = null
  let externalLinkHoverCallback: ((link: InternalLink | null) => void) | null = null
  let externalLinkClickCallback: ((link: InternalLink | null) => void) | null = null
  let bloomPassRef: UnrealBloomPass | null = null
  const bloomEnabled = ref(true)
  const activeSpeakerIds = new Set<string>()
  const pulseMap = new Map<string, number>()
  const PULSE_DECAY = 0.03

  // Camera focus priority queue
  const CAMERA_PRIORITY: Record<string, number> = {
    decision_locked: 4,
    alliance_formed: 3,
    stance_shifted: 2,
    claim_made: 1,
  }
  let pendingFocus: { nodeId: string; priority: number } | null = null
  let cameraFocusTimer: ReturnType<typeof setTimeout> | null = null

  function restartThinkingAnimation() {
    if (!sceneRef || internalNodes.length > 0) return

    if (thinkingCleanup) {
      thinkingCleanup()
      thinkingCleanup = null
    }

    thinkingCleanup = startThinkingAnimation(sceneRef, {
      mode: thinkingModeRef?.value ?? 'idle',
    })
  }

  function stopThinkingAnimation() {
    if (!thinkingCleanup) return
    thinkingCleanup()
    thinkingCleanup = null
  }

  function applySwimMotionToNode(node: InternalNode, group: THREE.Group, coords?: Position) {
    const basePosition = coords || getRenderedPosition(node)
    const motion = sampleSwimMotion({
      coords: toMotionVector(basePosition),
      velocity: {
        x: node.vx ?? 0,
        y: node.vy ?? 0,
        z: node.vz ?? 0,
      },
      time: performance.now() / 1000,
      state: node.swimState,
      activity: activeSpeakerIds.has(node.id) ? 1 : node.activity_score,
    })

    node.displayX = basePosition.x + motion.offset.x
    node.displayY = basePosition.y + motion.offset.y
    node.displayZ = basePosition.z + motion.offset.z
    group.position.set(node.displayX, node.displayY, node.displayZ)

    const motionRoot = group.getObjectByName('motionRoot') as THREE.Group | undefined
    if (motionRoot) {
      motionRoot.rotation.order = 'YXZ'
      motionRoot.rotation.set(motion.pitch, motion.yaw, motion.roll)
      const stretch = 1 + motion.thrust * 0.08
      const squash = 1 - motion.thrust * 0.035
      motionRoot.scale.set(squash, squash, stretch)
    }
  }

  function createNodeThreeObject(node: InternalNode): THREE.Object3D {
    const group = new THREE.Group()
    const motionRoot = new THREE.Group()
    motionRoot.name = 'motionRoot'
    group.add(motionRoot)

    // Shared geometry lookup
    const isKG = node.id.startsWith('kg-')
    const coreGeometry = isKG ? sharedOctaCore : sharedSphereCore
    const glowGeometry = isKG ? sharedOctaGlow : sharedSphereGlow

    // Agent nodes use ShaderMaterial with pulse uniform; KG nodes keep MeshStandardMaterial
    const isAgent = node.type === 'agent'
    const coreMaterial = isAgent
      ? new THREE.ShaderMaterial({
          transparent: true,
          vertexShader: PULSE_VERTEX,
          fragmentShader: PULSE_FRAGMENT,
          uniforms: {
            u_color: { value: new THREE.Color(node.color) },
            u_pulse: { value: 0.0 },
            u_emissiveIntensity: { value: 0.8 + node.importance_score * 0.6 },
            u_opacity: { value: 0.95 },
          },
        })
      : new THREE.MeshStandardMaterial({
          transparent: true,
          roughness: 0.15,
          metalness: 0.3,
        })

    const core = new THREE.Mesh(coreGeometry, coreMaterial)
    core.name = 'core'
    motionRoot.add(core)

    const innerGlow = new THREE.Mesh(
      glowGeometry,
      new THREE.MeshBasicMaterial({
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    innerGlow.name = 'innerGlow'
    motionRoot.add(innerGlow)

    const halo = new THREE.Mesh(
      glowGeometry,
      new THREE.MeshBasicMaterial({
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    )
    halo.name = 'halo'
    motionRoot.add(halo)

    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')!
    canvas.width = 256
    canvas.height = 64

    const texture = new THREE.CanvasTexture(canvas)
    texture.needsUpdate = true
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthWrite: false,
      }),
    )
    sprite.name = 'label'
    sprite.userData.canvas = canvas
    sprite.userData.context = ctx
    sprite.userData.texture = texture
    group.add(sprite)

    applyNodeThreeObjectVisuals(node, group, true)
    applySwimMotionToNode(node, group)
    if (options?.nodeExtension) {
      options.nodeExtension(node, group)
    }
    return group
  }

  function getGraphCenter() {
    return getGraphCenterFromNodes(internalNodes)
  }

  function resolveSpawnPosition(
    nodeId: string,
    edges: GraphEdge[],
    nodeMap: Map<string, PositionedNode>,
    fallbackCenter = getGraphCenter(),
  ) {
    const neighbors = edges
      .map((edge) => {
        if (edge.source === nodeId) return nodeMap.get(edge.target)
        if (edge.target === nodeId) return nodeMap.get(edge.source)
        return undefined
      })
      .filter(hasPosition)

    const base = neighbors.length
      ? neighbors.reduce(
          (acc, node) => ({
            x: acc.x + node.x,
            y: acc.y + node.y,
            z: acc.z + node.z,
          }),
          { x: 0, y: 0, z: 0 },
        )
      : fallbackCenter

    const divisor = neighbors.length || 1
    const spread = neighbors.length ? 10 : 18

    return {
      x: base.x / divisor + (Math.random() - 0.5) * spread,
      y: base.y / divisor + (Math.random() - 0.5) * spread,
      z: base.z / divisor + (Math.random() - 0.5) * spread,
    }
  }

  function buildInternalNode(
    node: GraphNode,
    seedPosition?: Position,
    existing?: Pick<InternalNode, 'swimState' | 'displayX' | 'displayY' | 'displayZ'>,
  ): InternalNode {
    const importanceScore = node.importance_score || 0.5
    const visuals = getNodeVisuals(node.type, importanceScore, node.stance, node.id)
    const position = seedPosition ?? { x: 0, y: 0, z: 0 }

    // KG nodes: Y-axis offset to create layered separation
    const isKG = node.id.startsWith('kg-')
    const yOffset = isKG ? -15 : 0

    return {
      id: node.id,
      label: node.label,
      type: node.type,
      importance_score: importanceScore,
      activity_score: node.activity_score || 0,
      color: visuals.color,
      size: visuals.size,
      opacity: DEFAULT_NODE_OPACITY,
      x: position.x,
      y: position.y + yOffset,
      z: position.z,
      displayX: existing?.displayX ?? position.x,
      displayY: existing?.displayY ?? (position.y + yOffset),
      displayZ: existing?.displayZ ?? position.z,
      swimState: existing?.swimState ?? createSwimMotionState(node.id, importanceScore, node.type),
    }
  }

  function createNebula(scene: THREE.Scene) {
    const nebulae = [
      { color: 0x6633cc, x: 250, y: 80, z: -200, count: 200 },
      { color: 0x3355aa, x: -200, y: -100, z: 180, count: 180 },
      { color: 0xcc33aa, x: 100, y: 200, z: 150, count: 160 },
      { color: 0x3333aa, x: -150, y: -50, z: -250, count: 220 },
    ]

    for (const neb of nebulae) {
      const positions = new Float32Array(neb.count * 3)

      for (let i = 0; i < neb.count; i++) {
        const spread = 120
        positions[i * 3] = neb.x + (Math.random() + Math.random() + Math.random() - 1.5) * spread
        positions[i * 3 + 1] = neb.y + (Math.random() + Math.random() + Math.random() - 1.5) * spread
        positions[i * 3 + 2] = neb.z + (Math.random() + Math.random() + Math.random() - 1.5) * spread
      }

      const geometry = new THREE.BufferGeometry()
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

      const material = new THREE.PointsMaterial({
        color: neb.color,
        size: 8,
        transparent: true,
        opacity: 0.04,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        sizeAttenuation: true,
      })

      const cloud = new THREE.Points(geometry, material)
      scene.add(cloud)
    }
  }

  let cameraInitialized = false
  let breathingInterval: ReturnType<typeof setInterval> | null = null

  function initGraph() {
    if (!containerRef.value) return
    if (graph.value && mountedContainer === containerRef.value) return

    const container = containerRef.value
    mountedContainer = container
    try {
      const width = container.clientWidth
      const height = container.clientHeight

      const fg = new ForceGraph3D(container)
        .width(width)
        .height(height)
        .backgroundColor('rgba(0,0,0,0)')
        .showNavInfo(false)
        .nodeThreeObject((node: any) => createNodeThreeObject(node as InternalNode))
        .nodeThreeObjectExtend(false)
        .nodePositionUpdate((nodeObj: THREE.Object3D, coords: Position, node: any) => {
          applySwimMotionToNode(node as InternalNode, nodeObj as THREE.Group, coords)
          return true
        })
        .linkWidth((link: any) => {
          const l = link as InternalLink
          const style = RELATION_TYPE_STYLES[l.relationType] || RELATION_TYPE_STYLES.default
          return Math.max(0.8, style.width + l.weight * 1.0)
        })
        .linkColor((link: any) => (link as InternalLink).color)
        .linkMaterial((link: any) => {
          const l = link as InternalLink
          const style = RELATION_TYPE_STYLES[l.relationType] || RELATION_TYPE_STYLES.default
          return new THREE.MeshBasicMaterial({
            color: style.color,
            transparent: true,
            opacity: l.opacity ?? DEFAULT_LINK_OPACITY,
            depthWrite: false,
          })
        })
        .linkDirectionalArrowRelPos(0.95)
        .linkDirectionalParticleWidth(2.0)
        .linkDirectionalParticleSpeed((link: any) => {
          const l = link as InternalLink
          const baseSpeed = 0.003 + l.weight * 0.008
          if (activeSpeakerIds.size === 0) return baseSpeed
          const srcId = typeof l.source === 'string' ? l.source : l.source.id
          const tgtId = typeof l.target === 'string' ? l.target : l.target.id
          return (activeSpeakerIds.has(srcId) || activeSpeakerIds.has(tgtId)) ? baseSpeed * 2 : baseSpeed
        })
        .linkCurvature((link: any) => {
          const l = link as InternalLink
          return l.weight > 0.7 ? 0.2 : 0.1
        })
        .d3AlphaDecay(GRAPH_LAYOUT.alphaDecay)
        .d3VelocityDecay(GRAPH_LAYOUT.velocityDecay)
        .warmupTicks(GRAPH_LAYOUT.warmupTicks)
        .cooldownTime(GRAPH_LAYOUT.cooldownTime)

      ;(fg as any)
        .linkOpacity((link: any) => (link as InternalLink).opacity ?? DEFAULT_LINK_OPACITY)
        .linkVisibility((link: any) => ((link as InternalLink).opacity ?? 0) > 0.02)
        .linkDirectionalArrowLength((link: any) => (((link as InternalLink).opacity ?? 0) > 0.05 ? 3 : 0))
        .linkDirectionalArrowColor((link: any) => (link as InternalLink).color)
        .linkDirectionalParticles((link: any) => {
          const l = link as InternalLink
          if (((l.opacity ?? 0) <= 0.12)) return 0
          const style = RELATION_TYPE_STYLES[l.relationType] || RELATION_TYPE_STYLES.default
          const base = Math.max(1, Math.ceil(style.width * 1.5))
          if (activeSpeakerIds.size > 0) {
            const srcId = typeof l.source === 'string' ? l.source : l.source.id
            const tgtId = typeof l.target === 'string' ? l.target : l.target.id
            if (activeSpeakerIds.has(srcId) || activeSpeakerIds.has(tgtId)) return base + 3
          }
          return base
        })
        .linkDirectionalParticleColor((link: any) => {
          const l = link as InternalLink
          const style = RELATION_TYPE_STYLES[l.relationType] || RELATION_TYPE_STYLES.default
          return style.particleColor
        })

      fg.d3Force('charge')?.strength((node: any) => {
        const n = node as InternalNode
        return n.importance_score > 0.8 ? -60 : GRAPH_LAYOUT.chargeStrength
      })
      fg.d3Force('link')?.distance((link: any) => {
        const l = link as InternalLink
        return 15 + (1 - l.weight) * 25
      })

      const renderer = fg.renderer() as THREE.WebGLRenderer
      renderer.toneMapping = THREE.ACESFilmicToneMapping
      renderer.toneMappingExposure = 0.9

      const camera = fg.camera() as THREE.PerspectiveCamera
      camera.far = 2000
      camera.updateProjectionMatrix()

      const scene = fg.scene()
      sceneRef = scene
      scene.fog = new THREE.FogExp2(0x020210, 0.0004)

      const ambientLight = new THREE.AmbientLight(0x080820, 1.6)
      scene.add(ambientLight)

      const purpleLight = new THREE.PointLight(0x9933ff, 1.5, 500)
      purpleLight.position.set(200, 100, -150)
      scene.add(purpleLight)

      const blueLight = new THREE.PointLight(0x3366ff, 1.2, 500)
      blueLight.position.set(-180, -80, 200)
      scene.add(blueLight)

      const cyanLight = new THREE.PointLight(0x00cccc, 1.0, 400)
      cyanLight.position.set(50, -150, -100)
      scene.add(cyanLight)

      createNebula(scene)

      // Bloom post-processing
      try {
        const bloomPass = new UnrealBloomPass(
          new THREE.Vector2(width, height),
          0.55,  // strength
          0.8,   // radius
          0.4,   // threshold
        )
        bloomPassRef = bloomPass
        fg.postProcessingComposer().addPass(bloomPass)
      } catch {
        // Graceful fallback if post-processing is unavailable
        bloomPassRef = null
      }

      const controls = fg.controls() as any
      controls.autoRotate = true
      controls.autoRotateSpeed = 0.3

      fg.onEngineStop(() => {
        if (!cameraInitialized) {
          cameraInitialized = true
          fg.cameraPosition({ x: 0, y: 50, z: 350 })
        }
        if (!breathingInterval && internalNodes.length > 0) {
          breathingInterval = setInterval(() => {
            if (internalNodes.length > 0) {
              ;(fg as any).d3AlphaTarget(0.015)
              setTimeout(() => (fg as any).d3AlphaTarget(0), 2000)
            }
          }, 4000)
        }
      })

      let tickCount = 0
      fg.onEngineTick(() => {
        tickCount++
        if (tickCount % 2 !== 0) return
        const time = performance.now() / 1000
        for (const node of internalNodes) {
          const group = node.__threeObj as THREE.Group | undefined
          if (!group) continue
          const core = group.getObjectByName('core') as THREE.Mesh | undefined
          if (!core) continue
          const phase = (node.id.charCodeAt(0) || 0) * 0.1
          const size = Math.max(node.size, MIN_NODE_SIZE)
          const breathScale = 1.0 + 0.03 * Math.sin(time * 1.5 + phase)
          core.scale.setScalar(size * 0.6 * breathScale)
          const halo = group.getObjectByName('halo') as THREE.Mesh | undefined
          if (halo) {
            halo.scale.setScalar(size * 2.8 * (1.0 + 0.05 * Math.sin(time * 1.2 + phase + 1)))
          }
        }

        // Pulse decay for ShaderMaterial nodes
        for (const [nodeId, value] of pulseMap.entries()) {
          const node = internalNodes.find(n => n.id === nodeId)
          if (!node) { pulseMap.delete(nodeId); continue }
          const group = node.__threeObj as THREE.Group | undefined
          const core = group?.getObjectByName('core') as THREE.Mesh | undefined
          if (core?.material instanceof THREE.ShaderMaterial) {
            core.material.uniforms.u_pulse.value = value
          }
          const next = value - PULSE_DECAY
          if (next <= 0) {
            pulseMap.delete(nodeId)
            if (core?.material instanceof THREE.ShaderMaterial) {
              core.material.uniforms.u_pulse.value = 0
            }
          } else {
            pulseMap.set(nodeId, next)
          }
        }
      })

      fg.onNodeClick((node: any) => {
        const n = node as InternalNode
        const focus = getRenderedPosition(n)
        const distance = 100
        const distRatio = 1 + distance / Math.hypot(focus.x || 0, focus.y || 0, focus.z || 0)
        fg.cameraPosition(
          { x: focus.x * distRatio, y: focus.y * distRatio, z: focus.z * distRatio },
          focus as any,
          1000,
        )
        if (externalNodeClickCallback) {
          externalNodeClickCallback(n.id)
        }
      })

      fg.onNodeHover((node: any) => {
        container.style.cursor = node ? 'pointer' : 'default'
      })

      fg.onLinkHover((link: any) => {
        if (!link) {
          if (externalLinkHoverCallback) externalLinkHoverCallback(null)
          return
        }
        container.style.cursor = 'pointer'
        if (externalLinkHoverCallback) externalLinkHoverCallback(link as InternalLink)
      })

      fg.onLinkClick((link: any) => {
        if (externalLinkClickCallback) {
          externalLinkClickCallback(link ? (link as InternalLink) : null)
        }
      })

      graphError.value = ''
      graph.value = fg
      syncGraphData()

      // Start thinking particles if no nodes yet
      restartThinkingAnimation()

      resizeObserver?.disconnect()
      resizeObserver = new ResizeObserver(() => {
        if (!containerRef.value || !graph.value) return
        const w = containerRef.value.clientWidth
        const h = containerRef.value.clientHeight
        graph.value.width(w).height(h)
        if (bloomPassRef) {
          bloomPassRef.setSize(w, h)
        }
      })
      resizeObserver.observe(container)
    } catch (error) {
      graph.value = null
      sceneRef = null
      mountedContainer = null
      graphError.value = 'この環境では 3D グラフを初期化できませんでした。WebGL が利用できない可能性があります。'
      console.error('Force graph initialization failed:', error)
    }
  }

  function syncGraphData(options: { reheat?: boolean } = {}) {
    if (!graph.value) return

    graph.value.graphData({
      nodes: [...internalNodes],
      links: [...internalLinks],
    })

    if (options.reheat && internalNodes.length > 0) {
      graph.value.d3ReheatSimulation()
    }
  }

  function refreshGraph() {
    if (!graph.value) return
    graph.value.refresh()
  }

  function animateGrowIn(node: InternalNode) {
    const targetSize = node.size
    const targetOpacity = node.opacity
    node.size = 0.1
    node.opacity = 0
    const startTime = performance.now()
    const duration = 400

    function tick() {
      const elapsed = performance.now() - startTime
      const t = Math.min(elapsed / duration, 1)
      const eased = 1 - (1 - t) * (1 - t) // easeOutQuad
      node.size = lerp(0.1, targetSize, eased)
      node.opacity = lerp(0, targetOpacity, eased)
      applyNodeThreeObjectVisuals(node)
      if (t < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }

  function applyDiff(diff: any) {
    activeTransition = null

    if (!graph.value) return

    if (diff.removed_nodes?.length) {
      const removeIds = new Set(diff.removed_nodes.map((n: any) => n.id))
      for (let i = internalNodes.length - 1; i >= 0; i--) {
        if (removeIds.has(internalNodes[i].id)) internalNodes.splice(i, 1)
      }
      for (let i = internalLinks.length - 1; i >= 0; i--) {
        const link = internalLinks[i]
        const src = typeof link.source === 'string' ? link.source : link.source.id
        const tgt = typeof link.target === 'string' ? link.target : link.target.id
        if (removeIds.has(src) || removeIds.has(tgt)) internalLinks.splice(i, 1)
      }
    }

    if (diff.removed_edges?.length) {
      const removeIds = new Set(diff.removed_edges.map((e: any) => e.id))
      for (let i = internalLinks.length - 1; i >= 0; i--) {
        if (removeIds.has(internalLinks[i].id)) internalLinks.splice(i, 1)
      }
    }

    const newNodes: InternalNode[] = []
    if (diff.added_nodes?.length) {
      const existing = new Set(internalNodes.map((n) => n.id))
      for (const n of diff.added_nodes) {
        if (!existing.has(n.id)) {
          const node = buildInternalNode(
            n,
            resolveSpawnPosition(
              n.id,
              (diff.added_edges || []).map((edge: any) => ({
                id: edge.id,
                source: edge.source,
                target: edge.target,
                relation_type: edge.relation_type || 'unknown',
                weight: edge.weight || 0.5,
                direction: edge.direction || 'directed',
                status: edge.status || 'active',
              })),
              new Map(internalNodes.map((node) => [node.id, node])),
            ),
            undefined,
          )
          internalNodes.push(node)
          newNodes.push(node)
        }
      }
    }

    if (diff.added_edges?.length) {
      const existing = new Set(internalLinks.map((l) => l.id))
      const nodeMap = new Map(internalNodes.map((node) => [node.id, node]))
      for (const e of diff.added_edges) {
        if (!existing.has(e.id)) {
          const relationType = e.relation_type || 'default'
          const style = RELATION_TYPE_STYLES[relationType] || RELATION_TYPE_STYLES.default
          internalLinks.push({
            id: e.id,
            source: e.source,
            target: e.target,
            weight: e.weight || 0.5,
            direction: e.direction || 'directed',
            color: relationType !== 'default' ? style.color : getLinkColor(e.source, nodeMap),
            opacity: DEFAULT_LINK_OPACITY,
            relationType,
          })
        }
      }
    }

    if (diff.updated_nodes?.length) {
      for (const u of diff.updated_nodes) {
        const node = internalNodes.find((n) => n.id === u.id)
        if (node) {
          updateInternalNode(node, {
            id: node.id,
            label: u.label ?? node.label,
            type: u.type ?? node.type,
            importance_score: u.importance_score ?? node.importance_score,
            activity_score: u.activity_score ?? node.activity_score,
            stance: '',
            sentiment_score: 0,
            status: '',
            group: '',
          })
          applyNodeThreeObjectVisuals(node)
        }
      }
    }

    if (diff.updated_edges?.length) {
      for (const u of diff.updated_edges) {
        const link = internalLinks.find((l) => l.id === u.id)
        if (link) {
          link.weight = u.weight ?? link.weight
          link.opacity = DEFAULT_LINK_OPACITY
        }
      }
    }

    syncGraphData({ reheat: true })

    // Grow-in animation for new nodes
    for (const node of newNodes) {
      animateGrowIn(node)
    }

    // Stop thinking particles on first nodes
    if (newNodes.length > 0) {
      stopThinkingAnimation()
    }
  }

  function setFullGraph(nodes: GraphNode[], edges: GraphEdge[]) {
    activeTransition = null

    if (nodes.length > 0) {
      stopThinkingAnimation()
    }

    const nodeMap = new Map(internalNodes.map((node) => [node.id, node]))

    const nextNodes = nodes.map((node) => {
      const existing = nodeMap.get(node.id)
      const position = hasPosition(existing)
        ? { x: existing.x, y: existing.y, z: existing.z }
        : resolveSpawnPosition(node.id, edges, nodeMap)
      const nextNode = buildInternalNode(node, position, existing)
      clearFixedPosition(nextNode)
      return nextNode
    })

    // Build a map from source GraphNodes that includes stance data for link coloring
    const graphNodeMap = new Map(nodes.map((n) => [n.id, n]))

    const nextLinks = edges.map((edge) => {
      const relationType = edge.relation_type || 'default'
      // Use relation type color if available, fall back to stance-aware coloring
      const style = RELATION_TYPE_STYLES[relationType] || RELATION_TYPE_STYLES.default
      const color = relationType !== 'default'
        ? style.color
        : getStanceAwareLinkColor(edge.source, edge.target, graphNodeMap as any)

      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        weight: edge.weight || 0.5,
        direction: edge.direction || 'directed',
        color,
        opacity: DEFAULT_LINK_OPACITY,
        relationType,
      }
    })

    internalNodes.length = 0
    internalNodes.push(...nextNodes)
    internalLinks.length = 0
    internalLinks.push(...nextLinks)

    syncGraphData({ reheat: true })

    if (nodes.length === 0) {
      restartThinkingAnimation()
    }
  }

  function buildTransitionNodeFrameFromInternal(node: InternalNode, position?: Position): TransitionNodeFrame {
    return {
      label: node.label,
      type: node.type,
      importance_score: node.importance_score,
      color: node.color,
      size: node.size,
      opacity: node.opacity ?? DEFAULT_NODE_OPACITY,
      x: position?.x ?? node.x,
      y: position?.y ?? node.y,
      z: position?.z ?? node.z,
    }
  }

  function buildTransitionNodeFrameFromGraph(
    node: GraphNode,
    position: Position,
    options: { opacity?: number; sizeMultiplier?: number } = {},
  ): TransitionNodeFrame {
    const importanceScore = node.importance_score || 0.5
    const visuals = getNodeVisuals(node.type, importanceScore, node.stance)

    return {
      label: node.label,
      type: node.type,
      importance_score: importanceScore,
      color: visuals.color,
      size: visuals.size * (options.sizeMultiplier ?? 1),
      opacity: options.opacity ?? DEFAULT_NODE_OPACITY,
      ...position,
    }
  }

  function buildTransitionLinkFrame(
    edge: GraphEdge,
    color: string,
    opacity = DEFAULT_LINK_OPACITY,
  ): TransitionLinkFrame {
    return {
      source: edge.source,
      target: edge.target,
      weight: edge.weight || 0.5,
      direction: edge.direction || 'directed',
      color,
      opacity,
      relationType: edge.relation_type || 'default',
    }
  }

  function resolveTargetLayout(
    nodes: GraphNode[],
    edges: GraphEdge[],
    seedNodeMap: Map<string, PositionedNode>,
  ) {
    const seedCenter = getGraphCenterFromNodes(Array.from(seedNodeMap.values()))
    const layoutNodeMap = new Map<string, LayoutNode>()
    const layoutNodes = nodes.map((node) => {
      const existing = seedNodeMap.get(node.id)
      const position = hasPosition(existing)
        ? { x: existing.x, y: existing.y, z: existing.z }
        : resolveSpawnPosition(node.id, edges, layoutNodeMap, seedCenter)

      const layoutNode: LayoutNode = {
        id: node.id,
        ...position,
        vx: 0,
        vy: 0,
        vz: 0,
      }
      layoutNodeMap.set(node.id, layoutNode)
      return layoutNode
    })

    for (let tick = 0; tick < TRANSITION_LAYOUT.ticks; tick++) {
      const forces = layoutNodes.map(() => ({ x: 0, y: 0, z: 0 }))

      for (let i = 0; i < layoutNodes.length; i++) {
        const a = layoutNodes[i]

        for (let j = i + 1; j < layoutNodes.length; j++) {
          const b = layoutNodes[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const dz = a.z - b.z
          const distanceSq = dx * dx + dy * dy + dz * dz + 0.01
          const distance = Math.sqrt(distanceSq)
          const strength = TRANSITION_LAYOUT.repulsion / distanceSq
          const fx = dx / distance * strength
          const fy = dy / distance * strength
          const fz = dz / distance * strength

          forces[i].x += fx
          forces[i].y += fy
          forces[i].z += fz
          forces[j].x -= fx
          forces[j].y -= fy
          forces[j].z -= fz
        }
      }

      for (const edge of edges) {
        const source = layoutNodeMap.get(edge.source)
        const target = layoutNodeMap.get(edge.target)
        if (!source || !target) continue

        const dx = target.x - source.x
        const dy = target.y - source.y
        const dz = target.z - source.z
        const distance = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.001
        const delta = distance - TRANSITION_LAYOUT.desiredDistance
        const strength = delta * TRANSITION_LAYOUT.attraction
        const fx = dx / distance * strength
        const fy = dy / distance * strength
        const fz = dz / distance * strength

        const sourceIndex = layoutNodes.indexOf(source)
        const targetIndex = layoutNodes.indexOf(target)
        forces[sourceIndex].x += fx
        forces[sourceIndex].y += fy
        forces[sourceIndex].z += fz
        forces[targetIndex].x -= fx
        forces[targetIndex].y -= fy
        forces[targetIndex].z -= fz
      }

      for (let i = 0; i < layoutNodes.length; i++) {
        const node = layoutNodes[i]
        forces[i].x += (seedCenter.x - node.x) * TRANSITION_LAYOUT.centering
        forces[i].y += (seedCenter.y - node.y) * TRANSITION_LAYOUT.centering
        forces[i].z += (seedCenter.z - node.z) * TRANSITION_LAYOUT.centering

        node.vx = clamp((node.vx + forces[i].x) * TRANSITION_LAYOUT.damping, -TRANSITION_LAYOUT.maxVelocity, TRANSITION_LAYOUT.maxVelocity)
        node.vy = clamp((node.vy + forces[i].y) * TRANSITION_LAYOUT.damping, -TRANSITION_LAYOUT.maxVelocity, TRANSITION_LAYOUT.maxVelocity)
        node.vz = clamp((node.vz + forces[i].z) * TRANSITION_LAYOUT.damping, -TRANSITION_LAYOUT.maxVelocity, TRANSITION_LAYOUT.maxVelocity)

        node.x += node.vx
        node.y += node.vy
        node.z += node.vz
      }
    }

    return new Map(layoutNodes.map((node) => [node.id, { x: node.x, y: node.y, z: node.z }]))
  }

  function startGraphTransition(
    fromNodes: GraphNode[],
    fromEdges: GraphEdge[],
    toNodes: GraphNode[],
    toEdges: GraphEdge[],
  ) {
    activeTransition = null

    const currentNodeMap = new Map(internalNodes.map((node) => [node.id, node]))
    const fromNodeMap = toGraphNodeMap(fromNodes)
    const toNodeMap = toGraphNodeMap(toNodes)
    const fromEdgeMap = toGraphEdgeMap(fromEdges)
    const toEdgeMap = toGraphEdgeMap(toEdges)
    const currentCenter = getGraphCenterFromNodes(Array.from(currentNodeMap.values()))
    const targetPositions = resolveTargetLayout(toNodes, toEdges, currentNodeMap)

    const transitionNodes: GraphTransitionNode[] = []
    const renderNodes: InternalNode[] = []
    const unionNodeIds = new Set<string>([
      ...fromNodeMap.keys(),
      ...toNodeMap.keys(),
    ])

    for (const nodeId of unionNodeIds) {
      const currentNode = currentNodeMap.get(nodeId)
      const fromGraphNode = fromNodeMap.get(nodeId)
      const toGraphNode = toNodeMap.get(nodeId)
      const sourcePosition = hasPosition(currentNode)
        ? { x: currentNode.x, y: currentNode.y, z: currentNode.z }
        : resolveSpawnPosition(nodeId, fromEdges, currentNodeMap, currentCenter)

      let renderNode: InternalNode
      let fromFrame: TransitionNodeFrame
      let toFrame: TransitionNodeFrame

      if (fromGraphNode && toGraphNode) {
        renderNode = buildInternalNode(fromGraphNode, sourcePosition, currentNode)
        fromFrame = currentNode
          ? buildTransitionNodeFrameFromInternal(currentNode, sourcePosition)
          : buildTransitionNodeFrameFromGraph(fromGraphNode, sourcePosition)
        toFrame = buildTransitionNodeFrameFromGraph(
          toGraphNode,
          targetPositions.get(nodeId) || sourcePosition,
        )
      } else if (toGraphNode) {
        const spawnPosition = resolveSpawnPosition(nodeId, toEdges, currentNodeMap, currentCenter)
        const targetPosition = targetPositions.get(nodeId) || spawnPosition
        renderNode = buildInternalNode(toGraphNode, spawnPosition, currentNode)
        fromFrame = buildTransitionNodeFrameFromGraph(toGraphNode, spawnPosition, {
          opacity: 0,
          sizeMultiplier: TRANSITION_LAYOUT.newNodeScaleFrom,
        })
        toFrame = buildTransitionNodeFrameFromGraph(toGraphNode, targetPosition)
      } else {
        const baseNode = currentNode || buildInternalNode(fromGraphNode!, sourcePosition)
        const driftTarget = {
          x: lerp(sourcePosition.x, currentCenter.x, TRANSITION_LAYOUT.removedNodeDrift),
          y: lerp(sourcePosition.y, currentCenter.y, TRANSITION_LAYOUT.removedNodeDrift),
          z: lerp(sourcePosition.z, currentCenter.z, TRANSITION_LAYOUT.removedNodeDrift),
        }
        renderNode = buildInternalNode(fromGraphNode!, sourcePosition, currentNode)
        fromFrame = buildTransitionNodeFrameFromInternal(baseNode, sourcePosition)
        toFrame = {
          ...buildTransitionNodeFrameFromInternal(baseNode, driftTarget),
          opacity: 0,
          size: Math.max(baseNode.size * TRANSITION_LAYOUT.removedNodeScaleTo, MIN_NODE_SIZE),
        }
      }

      transitionNodes.push({ node: renderNode, from: fromFrame, to: toFrame })
      renderNodes.push(renderNode)
    }

    const transitionLinks: GraphTransitionLink[] = []
    const renderLinks: InternalLink[] = []
    const unionEdgeIds = new Set<string>([
      ...fromEdgeMap.keys(),
      ...toEdgeMap.keys(),
    ])

    for (const edgeId of unionEdgeIds) {
      const fromEdge = fromEdgeMap.get(edgeId)
      const toEdge = toEdgeMap.get(edgeId)
      const basisEdge = toEdge || fromEdge
      if (!basisEdge) continue

      const renderLink: InternalLink = {
        id: edgeId,
        source: basisEdge.source,
        target: basisEdge.target,
        weight: basisEdge.weight || 0.5,
        direction: basisEdge.direction || 'directed',
        color: getLinkColor(basisEdge.source, toNodeMap, fromNodeMap, currentNodeMap),
        opacity: DEFAULT_LINK_OPACITY,
        relationType: basisEdge.relation_type || 'default',
      }

      const fromFrame = fromEdge
        ? buildTransitionLinkFrame(
            fromEdge,
            getLinkColor(fromEdge.source, fromNodeMap, currentNodeMap),
            DEFAULT_LINK_OPACITY,
          )
        : buildTransitionLinkFrame(
            toEdge!,
            getLinkColor(toEdge!.source, toNodeMap, currentNodeMap),
            0,
          )

      const toFrame = toEdge
        ? buildTransitionLinkFrame(
            toEdge,
            getLinkColor(toEdge.source, toNodeMap, currentNodeMap),
            DEFAULT_LINK_OPACITY,
          )
        : buildTransitionLinkFrame(
            fromEdge!,
            getLinkColor(fromEdge!.source, fromNodeMap, currentNodeMap),
            0,
          )

      transitionLinks.push({ link: renderLink, from: fromFrame, to: toFrame })
      renderLinks.push(renderLink)
    }

    activeTransition = {
      targetNodes: toNodes,
      targetEdges: toEdges,
      nodes: transitionNodes,
      links: transitionLinks,
    }

    internalNodes.length = 0
    internalNodes.push(...renderNodes)
    internalLinks.length = 0
    internalLinks.push(...renderLinks)

    syncGraphData()
    updateGraphTransition(0)
  }

  function updateGraphTransition(progress: number) {
    if (!activeTransition) return

    const normalized = clamp(progress, 0, 1)

    for (const transitionNode of activeTransition.nodes) {
      const { node, from, to } = transitionNode
      node.label = normalized < 0.5 ? from.label : to.label
      node.type = normalized < 0.5 ? from.type : to.type
      node.importance_score = lerp(from.importance_score, to.importance_score, normalized)
      node.color = lerpColor(from.color, to.color, normalized)
      node.size = Math.max(lerp(from.size, to.size, normalized), MIN_NODE_SIZE)
      node.opacity = lerp(from.opacity, to.opacity, normalized)

      const position = {
        x: lerp(from.x, to.x, normalized),
        y: lerp(from.y, to.y, normalized),
        z: lerp(from.z, to.z, normalized),
      }
      setFixedPosition(node, position)
      applyNodeThreeObjectVisuals(node)
    }

    for (const transitionLink of activeTransition.links) {
      const { link, from, to } = transitionLink
      link.source = normalized < 0.5 ? from.source : to.source
      link.target = normalized < 0.5 ? from.target : to.target
      link.weight = lerp(from.weight, to.weight, normalized)
      link.direction = normalized < 0.5 ? from.direction : to.direction
      link.color = lerpColor(from.color, to.color, normalized)
      link.opacity = lerp(from.opacity, to.opacity, normalized)
      link.relationType = normalized < 0.5 ? from.relationType : to.relationType
    }

    refreshGraph()
  }

  function finishGraphTransition() {
    if (!activeTransition) return

    const transition = activeTransition
    activeTransition = null
    setFullGraph(transition.targetNodes, transition.targetEdges)
  }

  function getNodeById(id: string) {
    return internalNodes.find((n) => n.id === id) || null
  }

  function resetCamera() {
    if (!graph.value) return
    graph.value.cameraPosition(
      { x: 0, y: 50, z: 350 },
      { x: 0, y: 0, z: 0 },
      800,
    )
  }

  onMounted(() => {
    initGraph()
  })

  watch(
    () => containerRef.value,
    (container) => {
      if (!container) return
      initGraph()
    },
  )

  if (thinkingModeRef) {
    watch(
      () => thinkingModeRef.value,
      () => {
        if (internalNodes.length === 0) {
          restartThinkingAnimation()
        }
      },
    )
  }

  onUnmounted(() => {
    if (cameraFocusTimer) {
      clearTimeout(cameraFocusTimer)
      cameraFocusTimer = null
    }
    if (breathingInterval) {
      clearInterval(breathingInterval)
      breathingInterval = null
    }
    resizeObserver?.disconnect()
    stopThinkingAnimation()
    graph.value?._destructor?.()
    graph.value = null
    graphError.value = ''
    mountedContainer = null
    activeTransition = null
    sceneRef = null
  })

  function onNodeClick(callback: ((nodeId: string) => void) | null) {
    externalNodeClickCallback = callback
  }

  function onLinkHover(callback: ((link: InternalLink | null) => void) | null) {
    externalLinkHoverCallback = callback
  }

  function onLinkClick(callback: ((link: InternalLink | null) => void) | null) {
    externalLinkClickCallback = callback
  }

  function setActiveSpeakers(ids: string[]) {
    activeSpeakerIds.clear()
    for (const id of ids) activeSpeakerIds.add(id)
  }

  function pulseNode(nodeId: string) {
    pulseMap.set(nodeId, 1.0)
  }

  function focusOnNode(nodeId: string, eventType: string) {
    const priority = CAMERA_PRIORITY[eventType] ?? 0
    if (pendingFocus && pendingFocus.priority > priority) return
    pendingFocus = { nodeId, priority }

    if (cameraFocusTimer) clearTimeout(cameraFocusTimer)
    cameraFocusTimer = setTimeout(() => {
      if (!graph.value || !pendingFocus) return
      const node = internalNodes.find(n => n.id === pendingFocus!.nodeId)
      if (!node) { pendingFocus = null; return }
      const focus = getRenderedPosition(node)
      const distance = 120
      const distRatio = 1 + distance / Math.max(Math.hypot(focus.x, focus.y, focus.z), 1)
      graph.value.cameraPosition(
        { x: focus.x * distRatio, y: focus.y * distRatio, z: focus.z * distRatio },
        focus as any,
        500,
      )
      pendingFocus = null
    }, 50)
  }

  function toggleBloom(enabled?: boolean) {
    const value = enabled ?? !bloomEnabled.value
    bloomEnabled.value = value
    if (bloomPassRef) {
      bloomPassRef.strength = value ? 0.55 : 0
    }
  }

  function getInternalNodes(): InternalNode[] {
    return internalNodes
  }

  return {
    graph,
    graphError,
    setFullGraph,
    applyDiff,
    startGraphTransition,
    updateGraphTransition,
    finishGraphTransition,
    getNodeById,
    resetCamera,
    onNodeClick,
    onLinkHover,
    onLinkClick,
    getInternalNodes,
    pulseNode,
    focusOnNode,
    toggleBloom,
    bloomEnabled,
    setActiveSpeakers,
  }
}
