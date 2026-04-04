import * as THREE from 'three'
import type { ForceGraph3DInstance } from '3d-force-graph'
import type { Ref } from 'vue'
import type { ConversationEdge } from '../stores/societyGraphStore'

const CONV_COLORS: Record<ConversationEdge['type'], string> = {
  question: '#00e5ff',
  response: '#ffd740',
  general: '#ffffff',
}

const CONV_OPACITY: Record<ConversationEdge['type'], number> = {
  question: 0.7,
  response: 0.55,
  general: 0.3,
}

const POOL_SIZE = 30
const PARTICLES_PER_LINE = 5
const ARC_HEIGHT_BASE = 15
const TUBE_RADIUS_DEFAULT = 0.15
const TUBE_RADIUS_ACTIVE: Record<ConversationEdge['type'], number> = {
  question: 0.25,
  response: 0.25,
  general: 0.15,
}
const TUBE_SEGMENTS = 20
const FADE_IN_MS = 500
const FADE_OUT_MS = 300

interface LineEntry {
  id: string
  sourceId: string
  targetId: string
  tube: THREE.Mesh
  particles: THREE.Points
  labelSprite: THREE.Sprite | null
  curve: THREE.QuadraticBezierCurve3
  material: THREE.MeshBasicMaterial
  particleMaterial: THREE.PointsMaterial
  type: ConversationEdge['type']
  createdAt: number
  fadingOut: boolean
  fadeOutStart: number
}

interface PoolEntry {
  tube: THREE.Mesh
  particles: THREE.Points
  inUse: boolean
}

const LABEL_MAP: Record<ConversationEdge['type'], string> = {
  question: 'Q',
  response: 'R',
  general: '',
}

function createConvLabelSprite(type: ConversationEdge['type']): THREE.Sprite | null {
  const label = LABEL_MAP[type]
  if (!label) return null

  const canvas = document.createElement('canvas')
  canvas.width = 64
  canvas.height = 64
  const ctx = canvas.getContext('2d')!

  // Background circle
  ctx.fillStyle = type === 'question' ? 'rgba(0, 229, 255, 0.7)' : 'rgba(255, 215, 64, 0.7)'
  ctx.beginPath()
  ctx.arc(32, 32, 24, 0, Math.PI * 2)
  ctx.fill()

  // Label text
  ctx.fillStyle = '#000000'
  ctx.font = 'bold 28px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, 32, 33)

  const texture = new THREE.CanvasTexture(canvas)
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(2.5, 2.5, 1)
  return sprite
}

function disposeLabelSprite(sprite: THREE.Sprite) {
  const material = sprite.material
  if (Array.isArray(material)) {
    for (const entry of material) {
      entry.map?.dispose()
      entry.dispose()
    }
    return
  }

  material.map?.dispose()
  material.dispose()
}

export function useConversationLines(
  graphRef: Ref<ForceGraph3DInstance | null>,
  getInternalNodes: () => Array<{ id: string; x: number; y: number; z: number }>,
) {
  const group = new THREE.Group()
  group.name = 'conversationLines'

  const activeLines = new Map<string, LineEntry>()
  const pool: PoolEntry[] = []
  let addedToScene = false

  // Pre-allocate pool
  for (let i = 0; i < POOL_SIZE; i++) {
    const tubeMat = new THREE.MeshBasicMaterial({
      transparent: true,
      opacity: 0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const tubeGeo = new THREE.BufferGeometry()
    const tube = new THREE.Mesh(tubeGeo, tubeMat)
    tube.visible = false

    const particleMat = new THREE.PointsMaterial({
      size: 1.8,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const positions = new Float32Array(PARTICLES_PER_LINE * 3)
    const particleGeo = new THREE.BufferGeometry()
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    const particles = new THREE.Points(particleGeo, particleMat)
    particles.visible = false

    group.add(tube)
    group.add(particles)
    pool.push({ tube, particles, inUse: false })
  }

  function ensureInScene() {
    if (addedToScene) return
    const fg = graphRef.value
    if (!fg) return
    const scene = fg.scene()
    if (scene) {
      scene.add(group)
      addedToScene = true
    }
  }

  function acquireFromPool(): PoolEntry | null {
    for (const entry of pool) {
      if (!entry.inUse) {
        entry.inUse = true
        return entry
      }
    }
    return null
  }

  function releaseToPool(entry: PoolEntry) {
    entry.tube.visible = false
    entry.particles.visible = false
    entry.inUse = false
  }

  function getNodePosition(nodeId: string): THREE.Vector3 | null {
    const nodes = getInternalNodes()
    const node = nodes.find((n) => n.id === nodeId)
    if (!node || !Number.isFinite(node.x)) return null
    return new THREE.Vector3(node.x, node.y, node.z)
  }

  function buildCurve(source: THREE.Vector3, target: THREE.Vector3, type: ConversationEdge['type']): THREE.QuadraticBezierCurve3 {
    const mid = new THREE.Vector3().addVectors(source, target).multiplyScalar(0.5)
    const heightMultiplier = type === 'question' ? 1.2 : type === 'response' ? 1.0 : 0.7
    mid.y += ARC_HEIGHT_BASE * heightMultiplier
    return new THREE.QuadraticBezierCurve3(source, mid, target)
  }

  function createLine(edge: ConversationEdge): LineEntry | null {
    const srcPos = getNodePosition(edge.source)
    const tgtPos = getNodePosition(edge.target)
    if (!srcPos || !tgtPos) return null

    const poolEntry = acquireFromPool()
    if (!poolEntry) return null

    const curve = buildCurve(srcPos, tgtPos, edge.type)
    const tubeRadius = TUBE_RADIUS_ACTIVE[edge.type] || TUBE_RADIUS_DEFAULT
    const tubeGeo = new THREE.TubeGeometry(curve, TUBE_SEGMENTS, tubeRadius, 4, false)

    // Replace geometry
    poolEntry.tube.geometry.dispose()
    poolEntry.tube.geometry = tubeGeo

    const tubeMat = poolEntry.tube.material as THREE.MeshBasicMaterial
    tubeMat.color.set(CONV_COLORS[edge.type])
    tubeMat.opacity = 0
    poolEntry.tube.visible = true

    const particleMat = poolEntry.particles.material as THREE.PointsMaterial
    particleMat.color.set(CONV_COLORS[edge.type])
    particleMat.opacity = 0
    poolEntry.particles.visible = true

    // Initialize particle positions along curve
    const posArr = poolEntry.particles.geometry.attributes.position as THREE.BufferAttribute
    for (let i = 0; i < PARTICLES_PER_LINE; i++) {
      const t = i / PARTICLES_PER_LINE
      const pt = curve.getPoint(t)
      posArr.setXYZ(i, pt.x, pt.y, pt.z)
    }
    posArr.needsUpdate = true

    // Label sprite at curve midpoint
    const labelSprite = createConvLabelSprite(edge.type)
    if (labelSprite) {
      const midPt = curve.getPoint(0.5)
      labelSprite.position.set(midPt.x, midPt.y + 1.5, midPt.z)
      group.add(labelSprite)
    }

    return {
      id: edge.id,
      sourceId: edge.source,
      targetId: edge.target,
      tube: poolEntry.tube,
      particles: poolEntry.particles,
      labelSprite,
      curve,
      material: tubeMat,
      particleMaterial: particleMat,
      type: edge.type,
      createdAt: performance.now(),
      fadingOut: false,
      fadeOutStart: 0,
    }
  }

  function syncEdges(edges: ConversationEdge[]) {
    ensureInScene()

    const edgeIds = new Set(edges.map((e) => e.id))

    // Mark removed lines for fade-out
    for (const [id, line] of activeLines) {
      if (!edgeIds.has(id) && !line.fadingOut) {
        line.fadingOut = true
        line.fadeOutStart = performance.now()
      }
    }

    // Add new lines
    for (const edge of edges) {
      if (!activeLines.has(edge.id)) {
        const line = createLine(edge)
        if (line) {
          activeLines.set(edge.id, line)
        }
      }
    }
  }

  function update(time: number) {
    const now = performance.now()
    const toRemove: string[] = []

    for (const [id, line] of activeLines) {
      if (line.fadingOut) {
        // Fade out
        const fadeProgress = Math.min(1, (now - line.fadeOutStart) / FADE_OUT_MS)
        const opacity = CONV_OPACITY[line.type] * (1 - fadeProgress)
        line.material.opacity = opacity
        line.particleMaterial.opacity = opacity
        if (line.labelSprite) line.labelSprite.material.opacity = opacity

        if (fadeProgress >= 1) {
          toRemove.push(id)
        }
        continue
      }

      // Fade in
      const fadeInProgress = Math.min(1, (now - line.createdAt) / FADE_IN_MS)
      const baseOpacity = CONV_OPACITY[line.type] * fadeInProgress

      // Pulse effect
      const pulse = 0.8 + 0.2 * Math.sin(time * 3)
      line.material.opacity = baseOpacity * pulse
      line.particleMaterial.opacity = baseOpacity * pulse * 1.2

      // Update curve positions (nodes may move)
      const srcPos = getNodePosition(line.sourceId)
      const tgtPos = getNodePosition(line.targetId)
      if (srcPos && tgtPos) {
        // Rebuild curve if nodes moved significantly
        const curveStart = line.curve.v0
        const dist = curveStart.distanceTo(srcPos)
        if (dist > 0.5) {
          const newCurve = buildCurve(srcPos, tgtPos, line.type)
          line.curve = newCurve
          const tubeRadius = TUBE_RADIUS_ACTIVE[line.type] || TUBE_RADIUS_DEFAULT
          const newGeo = new THREE.TubeGeometry(newCurve, TUBE_SEGMENTS, tubeRadius, 4, false)
          line.tube.geometry.dispose()
          line.tube.geometry = newGeo
        }
      }

      // Animate particles along curve from source to target.
      const posArr = line.particles.geometry.attributes.position as THREE.BufferAttribute
      for (let i = 0; i < PARTICLES_PER_LINE; i++) {
        const baseT = i / PARTICLES_PER_LINE
        const t = (baseT + time * 0.15) % 1
        const pt = line.curve.getPoint(t)
        posArr.setXYZ(i, pt.x, pt.y, pt.z)
      }
      posArr.needsUpdate = true

      // Update label sprite position
      if (line.labelSprite) {
        const midPt = line.curve.getPoint(0.5)
        line.labelSprite.position.set(midPt.x, midPt.y + 1.5, midPt.z)
        line.labelSprite.material.opacity = baseOpacity
      }
    }

    // Clean up fully faded lines
    for (const id of toRemove) {
      const line = activeLines.get(id)
      if (line) {
        if (line.labelSprite) {
          group.remove(line.labelSprite)
          disposeLabelSprite(line.labelSprite)
        }
        const poolEntry = pool.find((p) => p.tube === line.tube)
        if (poolEntry) releaseToPool(poolEntry)
        activeLines.delete(id)
      }
    }
  }

  function dispose() {
    for (const line of activeLines.values()) {
      if (line.labelSprite) {
        group.remove(line.labelSprite)
        disposeLabelSprite(line.labelSprite)
      }
    }
    for (const entry of pool) {
      entry.tube.geometry.dispose()
      ;(entry.tube.material as THREE.Material).dispose()
      entry.particles.geometry.dispose()
      ;(entry.particles.material as THREE.Material).dispose()
    }
    if (addedToScene) {
      const fg = graphRef.value
      if (fg) {
        const scene = fg.scene()
        scene?.remove(group)
      }
      addedToScene = false
    }
    activeLines.clear()
  }

  return {
    syncEdges,
    update,
    dispose,
  }
}
