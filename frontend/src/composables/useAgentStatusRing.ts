/**
 * Knowledge Graph モード用エージェントステータスリング。
 * useForceGraph の nodeExtension コールバックとして使用する。
 */
import * as THREE from 'three'
import type { InternalNode } from './useForceGraph'
import { useAgentVisualizationStore, type AgentVisualStatus } from '../stores/agentVisualizationStore'

const STATUS_RING_COLORS: Record<AgentVisualStatus, string> = {
  idle: '#00000000',
  thinking: '#3b82f6',
  executing: '#22c55e',
  speaking: '#ffd740',
  debating: '#f59e0b',
}

function createAgentStatusRing(): THREE.Mesh {
  const geometry = new THREE.RingGeometry(1.4, 1.7, 32)
  const material = new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  const ring = new THREE.Mesh(geometry, material)
  ring.name = 'agentStatusRing'
  return ring
}

export function useAgentStatusRing() {
  const vizStore = useAgentVisualizationStore()
  let animFrameId: number | null = null
  let animStartTime = 0
  let activeNodes: InternalNode[] = []

  function nodeExtension(node: InternalNode, group: THREE.Group) {
    if (node.type !== 'agent') return
    const ring = createAgentStatusRing()
    group.add(ring)
  }

  function startAnimationLoop(getInternalNodes: () => InternalNode[]) {
    if (animFrameId !== null) return
    animStartTime = performance.now()

    function tick() {
      const time = (performance.now() - animStartTime) / 1000
      activeNodes = getInternalNodes()

      for (const node of activeNodes) {
        if (node.type !== 'agent') continue
        const group = node.__threeObj as THREE.Group | undefined
        if (!group) continue

        const ring = group.getObjectByName('agentStatusRing') as THREE.Mesh | undefined
        if (!ring) continue

        const mat = ring.material as THREE.MeshBasicMaterial
        const status = vizStore.getAgentStatus(node.id)
        const color = STATUS_RING_COLORS[status] || STATUS_RING_COLORS.idle

        mat.color.set(color)

        if (status === 'thinking') {
          const pulse = 0.5 + 0.5 * Math.sin(time * 3)
          mat.opacity = 0.4 + pulse * 0.4
          ring.scale.setScalar(1.0 + pulse * 0.15)
        } else if (status === 'executing') {
          mat.opacity = 0.35
          ring.scale.setScalar(1.0)
        } else if (status === 'debating') {
          const pulse = 0.5 + 0.5 * Math.sin(time * 2)
          mat.opacity = 0.3 + pulse * 0.3
          ring.scale.setScalar(1.0 + pulse * 0.1)
        } else if (status === 'speaking') {
          const pulse = 0.5 + 0.5 * Math.sin(time * 4)
          mat.opacity = 0.5 + pulse * 0.4
          ring.scale.setScalar(1.0 + pulse * 0.2)
        } else {
          mat.opacity = 0
          ring.scale.setScalar(1.0)
        }
      }

      animFrameId = requestAnimationFrame(tick)
    }

    animFrameId = requestAnimationFrame(tick)
  }

  function stopAnimationLoop() {
    if (animFrameId !== null) {
      cancelAnimationFrame(animFrameId)
      animFrameId = null
    }
  }

  return {
    nodeExtension,
    startAnimationLoop,
    stopAnimationLoop,
  }
}
