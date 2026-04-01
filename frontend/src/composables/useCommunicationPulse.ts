import * as THREE from 'three'
import type { ForceGraph3DInstance } from '3d-force-graph'
import type { Ref } from 'vue'

export type PulseType = 'thinking' | 'communication' | 'debate'

const PULSE_COLORS: Record<PulseType, string> = {
  thinking: '#3b82f6',
  communication: '#22c55e',
  debate: '#f59e0b',
}

const PULSE_OPACITY: Record<PulseType, number> = {
  thinking: 0.6,
  communication: 0.5,
  debate: 0.55,
}

const POOL_SIZE = 20
const PARTICLES_PER_LINE = 5
const ARC_HEIGHT_BASE = 10
const TUBE_RADIUS = 0.12
const TUBE_SEGMENTS = 16
const FADE_IN_MS = 400
const FADE_OUT_MS = 500
const DEFAULT_DURATION_MS = 4000

interface PulseLineEntry {
  id: string
  sourceId: string
  targetId: string
  tube: THREE.Mesh
  particles: THREE.Points
  curve: THREE.QuadraticBezierCurve3
  material: THREE.MeshBasicMaterial
  particleMaterial: THREE.PointsMaterial
  type: PulseType
  createdAt: number
  expiresAt: number
  fadingOut: boolean
  fadeOutStart: number
}

interface PoolEntry {
  tube: THREE.Mesh
  particles: THREE.Points
  inUse: boolean
}

let pulseIdCounter = 0

export function useCommunicationPulse(
  graphRef: Ref<ForceGraph3DInstance | null>,
  getInternalNodes: () => Array<{ id: string; x: number; y: number; z: number }>,
) {
  const group = new THREE.Group()
  group.name = 'communicationPulseLines'

  const activeLines = new Map<string, PulseLineEntry>()
  const pool: PoolEntry[] = []
  let addedToScene = false

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
      size: 1.0,
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

  function buildCurve(source: THREE.Vector3, target: THREE.Vector3): THREE.QuadraticBezierCurve3 {
    const mid = new THREE.Vector3().addVectors(source, target).multiplyScalar(0.5)
    mid.y += ARC_HEIGHT_BASE
    return new THREE.QuadraticBezierCurve3(source, mid, target)
  }

  function addPulseLine(
    sourceId: string,
    targetId: string,
    type: PulseType,
    durationMs = DEFAULT_DURATION_MS,
  ): boolean {
    ensureInScene()

    const srcPos = getNodePosition(sourceId)
    const tgtPos = getNodePosition(targetId)
    if (!srcPos || !tgtPos) return false

    const poolEntry = acquireFromPool()
    if (!poolEntry) return false

    const curve = buildCurve(srcPos, tgtPos)
    const tubeGeo = new THREE.TubeGeometry(curve, TUBE_SEGMENTS, TUBE_RADIUS, 4, false)

    poolEntry.tube.geometry.dispose()
    poolEntry.tube.geometry = tubeGeo

    const tubeMat = poolEntry.tube.material as THREE.MeshBasicMaterial
    tubeMat.color.set(PULSE_COLORS[type])
    tubeMat.opacity = 0
    poolEntry.tube.visible = true

    const particleMat = poolEntry.particles.material as THREE.PointsMaterial
    particleMat.color.set(PULSE_COLORS[type])
    particleMat.opacity = 0
    poolEntry.particles.visible = true

    const posArr = poolEntry.particles.geometry.attributes.position as THREE.BufferAttribute
    for (let i = 0; i < PARTICLES_PER_LINE; i++) {
      const t = i / PARTICLES_PER_LINE
      const pt = curve.getPoint(t)
      posArr.setXYZ(i, pt.x, pt.y, pt.z)
    }
    posArr.needsUpdate = true

    const now = performance.now()
    const id = `pulse-${++pulseIdCounter}`
    activeLines.set(id, {
      id,
      sourceId,
      targetId,
      tube: poolEntry.tube,
      particles: poolEntry.particles,
      curve,
      material: tubeMat,
      particleMaterial: particleMat,
      type,
      createdAt: now,
      expiresAt: now + durationMs,
      fadingOut: false,
      fadeOutStart: 0,
    })

    return true
  }

  function update(time: number) {
    const now = performance.now()
    const toRemove: string[] = []

    for (const [id, line] of activeLines) {
      // Auto-expire
      if (!line.fadingOut && now >= line.expiresAt) {
        line.fadingOut = true
        line.fadeOutStart = now
      }

      if (line.fadingOut) {
        const fadeProgress = Math.min(1, (now - line.fadeOutStart) / FADE_OUT_MS)
        const opacity = PULSE_OPACITY[line.type] * (1 - fadeProgress)
        line.material.opacity = opacity
        line.particleMaterial.opacity = opacity
        if (fadeProgress >= 1) {
          toRemove.push(id)
        }
        continue
      }

      // Fade in
      const fadeInProgress = Math.min(1, (now - line.createdAt) / FADE_IN_MS)
      const baseOpacity = PULSE_OPACITY[line.type] * fadeInProgress

      // Pulse effect
      const pulse = 0.8 + 0.2 * Math.sin(time * 4)
      line.material.opacity = baseOpacity * pulse
      line.particleMaterial.opacity = baseOpacity * pulse * 1.2

      // Animate particles along curve
      const posArr = line.particles.geometry.attributes.position as THREE.BufferAttribute
      for (let i = 0; i < PARTICLES_PER_LINE; i++) {
        const baseT = i / PARTICLES_PER_LINE
        const t = (baseT + time * 0.2) % 1
        const pt = line.curve.getPoint(t)
        posArr.setXYZ(i, pt.x, pt.y, pt.z)
      }
      posArr.needsUpdate = true
    }

    for (const id of toRemove) {
      const line = activeLines.get(id)
      if (line) {
        const poolEntry = pool.find((p) => p.tube === line.tube)
        if (poolEntry) releaseToPool(poolEntry)
        activeLines.delete(id)
      }
    }
  }

  function dispose() {
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
    addPulseLine,
    update,
    dispose,
  }
}
