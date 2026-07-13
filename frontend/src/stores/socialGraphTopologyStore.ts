import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import type {
  GraphActivityEvent,
  GraphStateResponse,
  PopulationNetworkResponse,
  SocialGraphEdge,
  SocialGraphNode,
} from '../api/client'

export interface SocialTopologyNode extends SocialGraphNode {
  status: string
  activity: number
  role: 'representative' | 'expert' | 'population'
}

export interface SocialTopologyEdge extends SocialGraphEdge {
  activity: number
  last_changed_event_id?: number
}

export const useSocialGraphTopologyStore = defineStore('socialGraphTopology', () => {
  const simulationId = ref('')
  const nodes = ref<Map<string, SocialTopologyNode>>(new Map())
  const edges = ref<Map<string, SocialTopologyEdge>>(new Map())
  const populationNetwork = ref<PopulationNetworkResponse | null>(null)
  const currentPhase = ref('pending')
  const currentRound = ref(0)
  const snapshotCursor = ref(0)
  const lastAppliedEventId = ref(0)
  const appliedEventIds = new Set<number>()

  const selectedNodes = computed(() => Array.from(nodes.value.values()))
  const socialEdges = computed(() => Array.from(edges.value.values()))
  const activeNodeCount = computed(() => selectedNodes.value.filter((node) => node.activity > 0).length)

  function hydrate(snapshot: GraphStateResponse) {
    simulationId.value = snapshot.simulation_id
    nodes.value = new Map(snapshot.nodes.map((node) => [
      node.id,
      {
        ...node,
        status: node.stance ? 'activated' : 'selected',
        activity: 0,
        role: (
          ['医師', '研究者', '大学教授', '専門家'].some((label) => (
            node.demographics?.occupation?.includes(label)
          ))
            ? 'expert'
            : 'representative'
        ) as SocialTopologyNode['role'],
      },
    ]))
    edges.value = new Map(snapshot.edges.map((edge) => [
      edge.id,
      { ...edge, activity: 0 },
    ]))
    populationNetwork.value = snapshot.population_network
    currentPhase.value = snapshot.current_phase
    currentRound.value = snapshot.current_round
    snapshotCursor.value = snapshot.latest_event_id
    lastAppliedEventId.value = snapshot.latest_event_id
    appliedEventIds.clear()
  }

  function updateNode(nodeId: string | null | undefined, patch: Partial<SocialTopologyNode>) {
    if (!nodeId) return
    const existing = nodes.value.get(nodeId)
    if (!existing) return
    nodes.value = new Map(nodes.value).set(nodeId, { ...existing, ...patch })
  }

  function applyRelationshipChange(event: GraphActivityEvent) {
    if (!event.edge_id) return
    const existing = edges.value.get(event.edge_id)
    const afterStrength = Number(event.payload.after_strength ?? existing?.strength ?? 0)
    const source = event.source_id ?? existing?.source
    const target = event.target_id ?? existing?.target
    if (!source || !target) return
    const next: SocialTopologyEdge = {
      id: event.edge_id,
      source,
      target,
      relation_type: String(event.payload.relation_type ?? existing?.relation_type ?? 'acquaintance'),
      strength: afterStrength,
      activity: 1,
      last_changed_event_id: event.id,
    }
    edges.value = new Map(edges.value).set(event.edge_id, next)
  }

  function applyEvent(event: GraphActivityEvent) {
    if (event.simulation_id !== simulationId.value || appliedEventIds.has(event.id)) return false
    appliedEventIds.add(event.id)
    lastAppliedEventId.value = Math.max(lastAppliedEventId.value, event.id)
    currentPhase.value = event.phase
    currentRound.value = event.round
    nodes.value = new Map(Array.from(nodes.value.entries()).map(([id, node]) => [id, {
      ...node,
      activity: 0,
      status: node.status === 'speaking' ? 'activated' : node.status,
    }]))
    edges.value = new Map(Array.from(edges.value.entries()).map(([id, edge]) => [
      id,
      { ...edge, activity: 0 },
    ]))

    if (event.kind === 'node_status') {
      updateNode(event.source_id, {
        status: String(event.payload.status ?? 'active'),
        stance: String(event.payload.stance ?? nodes.value.get(event.source_id ?? '')?.stance ?? ''),
        confidence: Number(event.payload.confidence ?? nodes.value.get(event.source_id ?? '')?.confidence ?? 0.5),
        activity: 0.45,
      })
    } else if (event.kind === 'dialogue' || event.kind === 'influence') {
      updateNode(event.source_id, { activity: 1, status: event.kind === 'dialogue' ? 'speaking' : 'active' })
      updateNode(event.target_id, { activity: 0.65 })
      if (event.edge_id) {
        const edge = edges.value.get(event.edge_id)
        if (edge) edges.value = new Map(edges.value).set(event.edge_id, { ...edge, activity: 1 })
      }
    } else if (event.kind === 'stance_shift') {
      updateNode(event.source_id, {
        stance: String(event.payload.after_stance ?? ''),
        status: 'activated',
        activity: 0.85,
      })
    } else if (event.kind === 'relationship_changed') {
      applyRelationshipChange(event)
    }
    return true
  }

  function setPopulationNetwork(network: PopulationNetworkResponse) {
    populationNetwork.value = network
  }

  function reset() {
    simulationId.value = ''
    nodes.value = new Map()
    edges.value = new Map()
    populationNetwork.value = null
    currentPhase.value = 'pending'
    currentRound.value = 0
    snapshotCursor.value = 0
    lastAppliedEventId.value = 0
    appliedEventIds.clear()
  }

  return {
    simulationId,
    nodes,
    edges,
    populationNetwork,
    currentPhase,
    currentRound,
    snapshotCursor,
    lastAppliedEventId,
    selectedNodes,
    socialEdges,
    activeNodeCount,
    hydrate,
    applyEvent,
    setPopulationNetwork,
    reset,
  }
})
