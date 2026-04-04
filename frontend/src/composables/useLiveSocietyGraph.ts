import { ref, watch, onUnmounted, type Ref } from 'vue'
import * as THREE from 'three'
import { useForceGraph, type InternalNode } from './useForceGraph'
import { useSocietyGraphStore, STANCE_COLORS, type LiveAgentStatus } from '../stores/societyGraphStore'
import { useKGEvolutionStore } from '../stores/kgEvolutionStore'
import { useConversationLines } from './useConversationLines'
import type { ThinkingVisualMode } from './useThinkingParticles'

const STATUS_RING_COLORS: Record<LiveAgentStatus, string> = {
  selected: '#ffffff',
  activating: '#00e5ff',
  activated: '#66bb6a',
  speaking: '#ffd740',
  idle: '#00000000',
}

function createStatusRing(): THREE.Mesh {
  const geometry = new THREE.RingGeometry(1.4, 1.7, 32)
  const material = new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 0,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
  const ring = new THREE.Mesh(geometry, material)
  ring.name = 'statusRing'
  return ring
}

function createSpeechBubbleSprite(): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 128
  const texture = new THREE.CanvasTexture(canvas)
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  })
  const sprite = new THREE.Sprite(material)
  sprite.name = 'speechBubble'
  sprite.visible = false
  sprite.scale.set(16, 4, 1)
  sprite.userData.canvas = canvas
  sprite.userData.texture = texture
  return sprite
}

function renderSpeechBubbleText(sprite: THREE.Sprite, text: string | null) {
  const canvas = sprite.userData.canvas as HTMLCanvasElement
  const ctx = canvas.getContext('2d')!
  const texture = sprite.userData.texture as THREE.CanvasTexture

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  if (!text) {
    sprite.visible = false
    texture.needsUpdate = true
    return
  }

  // Background
  const padding = 12
  const radius = 10
  ctx.fillStyle = 'rgba(20, 20, 35, 0.88)'
  ctx.beginPath()
  ctx.roundRect(padding, padding, canvas.width - padding * 2, canvas.height - padding * 2, radius)
  ctx.fill()
  ctx.strokeStyle = 'rgba(255, 215, 64, 0.5)'
  ctx.lineWidth = 2
  ctx.stroke()

  // Text
  ctx.fillStyle = '#e0e0e0'
  ctx.font = '22px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const displayText = text.length > 100 ? text.slice(0, 97) + '...' : text
  ctx.fillText(displayText, canvas.width / 2, canvas.height / 2)

  sprite.visible = true
  texture.needsUpdate = true
}

export function useLiveSocietyGraph(
  containerRef: Ref<HTMLElement | null>,
  thinkingModeRef: Ref<ThinkingVisualMode>,
) {
  const societyGraphStore = useSocietyGraphStore()
  const selectedAgentId = ref<string | null>(null)

  let animFrameId: number | null = null
  let animStartTime = 0

  // Node extension: add status ring and speech bubble to each node
  function nodeExtension(node: InternalNode, group: THREE.Group) {
    const ring = createStatusRing()
    group.add(ring)

    const bubble = createSpeechBubbleSprite()
    bubble.position.set(0, node.size * 3 + 4, 0)
    group.add(bubble)
  }

  const forceGraph = useForceGraph(containerRef, thinkingModeRef, { nodeExtension })

  // Conversation lines overlay
  const convLines = useConversationLines(forceGraph.graph, forceGraph.getInternalNodes)

  // Sync conversation edges from store
  watch(
    () => societyGraphStore.conversationEdges,
    (edges) => convLines.syncEdges(edges),
    { deep: true },
  )

  // Stance shift animations
  const stanceShiftAnimations = new Map<string, {
    fromColor: THREE.Color
    toColor: THREE.Color
    startTime: number
    duration: number
    shockwave: THREE.Mesh | null
  }>()

  watch(
    () => societyGraphStore.pendingStanceShifts,
    (shifts) => {
      if (!shifts.length) return
      const now = performance.now()
      const internalNodes = forceGraph.getInternalNodes()

      for (const shift of shifts) {
        const node = internalNodes.find((n) => n.id === shift.agentId)
        if (!node) continue

        const fromColor = new THREE.Color(STANCE_COLORS[shift.fromStance] || '#a3a3a3')
        const toColor = new THREE.Color(STANCE_COLORS[shift.toStance] || '#a3a3a3')

        // Create shockwave ring at node position
        let shockwave: THREE.Mesh | null = null
        const fg = forceGraph.graph.value
        if (fg && node.__threeObj) {
          const ringGeo = new THREE.RingGeometry(1, 1.5, 32)
          const ringMat = new THREE.MeshBasicMaterial({
            color: toColor,
            transparent: true,
            opacity: 0.8,
            side: THREE.DoubleSide,
            depthWrite: false,
            blending: THREE.AdditiveBlending,
          })
          shockwave = new THREE.Mesh(ringGeo, ringMat)
          shockwave.position.set(node.x || 0, node.y || 0, node.z || 0)
          fg.scene().add(shockwave)
        }

        stanceShiftAnimations.set(shift.agentId, {
          fromColor,
          toColor,
          startTime: now,
          duration: 1500,
          shockwave,
        })
      }

      // Clear after processing
      setTimeout(() => societyGraphStore.clearStanceShifts(), 100)
    },
    { deep: true },
  )

  // Update graph when store data changes
  watch(
    () => [societyGraphStore.graphNodes, societyGraphStore.graphEdges] as const,
    ([nodes, edges]) => {
      if (nodes.length > 0) {
        forceGraph.setFullGraph(nodes, edges)
      }
    },
    { deep: true },
  )

  // Sync interaction counts to edge widths
  watch(
    () => societyGraphStore.interactionMatrix,
    (matrix) => forceGraph.updateInteractionCounts(matrix),
    { deep: true },
  )

  // Animate status rings and speech bubbles
  function startAnimationLoop() {
    if (animFrameId !== null) return
    animStartTime = performance.now()

    function tick() {
      const time = (performance.now() - animStartTime) / 1000
      const internalNodes = forceGraph.getInternalNodes()

      for (const node of internalNodes) {
        const group = node.__threeObj as THREE.Group | undefined
        if (!group) continue

        const ring = group.getObjectByName('statusRing') as THREE.Mesh | undefined
        const bubble = group.getObjectByName('speechBubble') as THREE.Sprite | undefined
        if (!ring && !bubble) continue

        // Find agent data from store
        const agentData = societyGraphStore.liveAgents.get(node.id)
        if (!agentData) continue

        // Update status ring
        if (ring) {
          const mat = ring.material as THREE.MeshBasicMaterial
          const status = agentData.status
          const stance = agentData.stance

          // Color: use stance color for activated, otherwise status color
          const ringColor = status === 'activated' && stance
            ? (STANCE_COLORS[stance] || STATUS_RING_COLORS.activated)
            : STATUS_RING_COLORS[status] || STATUS_RING_COLORS.idle

          mat.color.set(ringColor)

          // Opacity and scale based on status
          if (status === 'speaking') {
            const pulse = 0.5 + 0.5 * Math.sin(time * 4)
            mat.opacity = 0.6 + pulse * 0.4
            ring.scale.setScalar(1.0 + pulse * 0.2)
          } else if (status === 'activating') {
            const pulse = 0.5 + 0.5 * Math.sin(time * 3)
            mat.opacity = 0.3 + pulse * 0.4
            ring.scale.setScalar(1.0 + pulse * 0.1)
          } else if (status === 'selected') {
            mat.opacity = 0.2
            ring.scale.setScalar(1.0)
          } else if (status === 'activated') {
            mat.opacity = 0.35
            ring.scale.setScalar(1.0)
          } else {
            mat.opacity = 0
          }
        }

        // Update speech bubble
        if (bubble) {
          if (agentData.status === 'speaking' && agentData.speakingText) {
            renderSpeechBubbleText(bubble, agentData.speakingText)
            bubble.position.set(0, (node.size || 3) * 3 + 5, 0)
          } else if (bubble.visible) {
            renderSpeechBubbleText(bubble, null)
          }
        }
      }

      // Update conversation arc lines
      convLines.update(time)

      // Update stance shift animations
      const now = performance.now()
      for (const [agentId, anim] of stanceShiftAnimations) {
        const progress = Math.min(1, (now - anim.startTime) / anim.duration)
        const node = internalNodes.find((n) => n.id === agentId)
        if (!node) continue

        const group = node.__threeObj as THREE.Group | undefined
        if (!group) continue

        // Color morph on core sphere
        const core = group.getObjectByName('core') as THREE.Mesh | undefined
        if (core) {
          const mat = core.material as THREE.MeshStandardMaterial
          const lerpedColor = anim.fromColor.clone().lerp(anim.toColor, progress)
          mat.color.copy(lerpedColor)
          mat.emissive.copy(lerpedColor)

          // Node pulse: scale bounce
          if (progress < 0.4) {
            const pulseT = progress / 0.4
            const scale = 1 + 0.4 * Math.sin(pulseT * Math.PI)
            core.scale.setScalar((node.size || 3) * 0.6 * scale)
          }
        }

        // Shockwave expand and fade
        if (anim.shockwave) {
          const swProgress = Math.min(1, (now - anim.startTime) / 800)
          const scale = 1 + swProgress * 4
          anim.shockwave.scale.setScalar(scale)
          const swMat = anim.shockwave.material as THREE.MeshBasicMaterial
          swMat.opacity = 0.8 * (1 - swProgress)
          anim.shockwave.position.set(node.x || 0, node.y || 0, node.z || 0)

          if (swProgress >= 1) {
            const fg = forceGraph.graph.value
            if (fg) {
              fg.scene().remove(anim.shockwave)
            }
            anim.shockwave.geometry.dispose()
            ;(anim.shockwave.material as THREE.Material).dispose()
            anim.shockwave = null
          }
        }

        // Animation complete
        if (progress >= 1) {
          stanceShiftAnimations.delete(agentId)
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

  // Start animation loop when nodes exist
  watch(
    () => societyGraphStore.nodeCount,
    (count) => {
      if (count > 0) {
        startAnimationLoop()
      } else {
        stopAnimationLoop()
      }
    },
    { immediate: true },
  )

  // Update active speakers for particle enhancement
  watch(
    () => societyGraphStore.speakingAgents,
    (speakers) => {
      forceGraph.setActiveSpeakers(speakers.map((a) => a.id))
    },
    { deep: true },
  )

  // Focus camera on speaking agent
  watch(
    () => societyGraphStore.speakingAgents,
    (speakers) => {
      if (speakers.length === 0) return
      const speakingAgent = speakers[0]
      const internalNodes = forceGraph.getInternalNodes()
      const node = internalNodes.find(n => n.id === speakingAgent.id)
      if (node && forceGraph.graph.value) {
        forceGraph.graph.value.cameraPosition(
          { x: node.x + 50, y: node.y + 30, z: node.z + 50 },
          node,
          1000,
        )
      }
    },
    { deep: true },
  )

  // Handle node click with KG entity highlighting
  let highlightedNodeIds: Set<string> | null = null

  function clearHighlight() {
    if (!highlightedNodeIds) return
    const allNodes = forceGraph.getInternalNodes()
    for (const n of allNodes) {
      n.opacity = 1.0
    }
    highlightedNodeIds = null
  }

  function highlightAgentsForEntity(entityId: string) {
    const kgStore = useKGEvolutionStore()
    const highlighted = new Set([entityId, ...kgStore.getAgentsForEntity(entityId)])

    clearHighlight()
    highlightedNodeIds = highlighted

    const allNodes = forceGraph.getInternalNodes()
    for (const n of allNodes) {
      n.opacity = highlighted.has(n.id) ? 1.0 : 0.15
    }
  }

  forceGraph.onNodeClick((nodeId: string) => {
    // If clicking same node, deselect
    if (selectedAgentId.value === nodeId) {
      selectedAgentId.value = null
      clearHighlight()
      return
    }

    selectedAgentId.value = nodeId

    // If clicking a KG entity, highlight related agents
    if (nodeId.startsWith('kg-')) {
      highlightAgentsForEntity(nodeId)
    } else {
      clearHighlight()
    }
  })

  // Handle link hover/click for edge info
  forceGraph.onLinkHover((link) => {
    if (!link) {
      societyGraphStore.setHoveredEdge(null)
      return
    }
    const sourceId = typeof link.source === 'string' ? link.source : link.source.id
    const targetId = typeof link.target === 'string' ? link.target : link.target.id
    societyGraphStore.setHoveredEdge({
      id: link.id,
      relationType: link.relationType,
      weight: link.weight,
      sourceId,
      targetId,
    })
  })

  forceGraph.onLinkClick((link) => {
    if (!link) {
      societyGraphStore.setSelectedEdge(null)
      return
    }
    const sourceId = typeof link.source === 'string' ? link.source : link.source.id
    const targetId = typeof link.target === 'string' ? link.target : link.target.id
    societyGraphStore.setSelectedEdge({
      id: link.id,
      relationType: link.relationType,
      weight: link.weight,
      sourceId,
      targetId,
    })
  })

  onUnmounted(() => {
    stopAnimationLoop()
    convLines.dispose()
  })

  return {
    ...forceGraph,
    selectedAgentId,
    highlightAgentsForEntity,
    clearHighlight,
  }
}
