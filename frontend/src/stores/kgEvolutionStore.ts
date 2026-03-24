import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { GraphNode, GraphEdge } from './graphStore'

export interface KGEntityNode {
  id: string
  label: string
  type: string
  importanceScore: number
  round: number
}

export interface KGRelationEdge {
  id: string
  source: string
  target: string
  relationType: string
  weight: number
  round: number
}

interface AgentEntityLink {
  agentId: string
  entityId: string
}

export const useKGEvolutionStore = defineStore('kgEvolution', () => {
  const entities = ref<Map<string, KGEntityNode>>(new Map())
  const relations = ref<Map<string, KGRelationEdge>>(new Map())
  const agentEntityLinks = ref<Map<string, string[]>>(new Map()) // agentId -> entityIds[]
  const layerVisible = ref(false)
  const currentRound = ref(-1)

  // === Computed ===

  const entityCount = computed(() => entities.value.size)
  const relationCount = computed(() => relations.value.size)

  const graphNodes = computed<GraphNode[]>(() =>
    Array.from(entities.value.values()).map((e) => ({
      id: e.id,
      label: e.label,
      type: e.type,
      importance_score: e.importanceScore,
      stance: '',
      activity_score: 0,
      sentiment_score: 0,
      status: 'active',
      group: 'knowledge',
    })),
  )

  const graphEdges = computed<GraphEdge[]>(() =>
    Array.from(relations.value.values()).map((r) => ({
      id: r.id,
      source: r.source,
      target: r.target,
      relation_type: r.relationType,
      weight: r.weight,
      direction: 'directed',
      status: 'active',
    })),
  )

  const agentEntityEdges = computed<GraphEdge[]>(() => {
    const edges: GraphEdge[] = []
    for (const [agentId, entityIds] of agentEntityLinks.value) {
      for (const entityId of entityIds) {
        edges.push({
          id: `link-${agentId}-${entityId}`,
          source: agentId,
          target: entityId,
          relation_type: 'mentions',
          weight: 0.3,
          direction: 'directed',
          status: 'active',
        })
      }
    }
    return edges
  })

  // === Actions ===

  function applyDiff(diff: {
    added_nodes?: Array<Record<string, any>>
    updated_nodes?: Array<Record<string, any>>
    removed_nodes?: Array<{ id: string }>
    added_edges?: Array<Record<string, any>>
    updated_edges?: Array<Record<string, any>>
    removed_edges?: Array<{ id: string }>
  }, roundNumber?: number) {
    if (roundNumber !== undefined) {
      currentRound.value = roundNumber
    }

    // Remove nodes
    if (diff.removed_nodes?.length) {
      for (const n of diff.removed_nodes) {
        entities.value.delete(n.id)
      }
    }

    // Add nodes
    if (diff.added_nodes?.length) {
      for (const n of diff.added_nodes) {
        if (!entities.value.has(n.id)) {
          entities.value.set(n.id, {
            id: n.id,
            label: n.label || '',
            type: n.type || 'concept',
            importanceScore: n.importance_score ?? 0.5,
            round: roundNumber ?? currentRound.value,
          })
        }
      }
    }

    // Update nodes
    if (diff.updated_nodes?.length) {
      for (const u of diff.updated_nodes) {
        const existing = entities.value.get(u.id)
        if (existing) {
          if (u.importance_score !== undefined) existing.importanceScore = u.importance_score
          if (u.label !== undefined) existing.label = u.label
          if (u.type !== undefined) existing.type = u.type
        }
      }
    }

    // Remove edges
    if (diff.removed_edges?.length) {
      for (const e of diff.removed_edges) {
        relations.value.delete(e.id)
      }
    }

    // Add edges
    if (diff.added_edges?.length) {
      for (const e of diff.added_edges) {
        if (!relations.value.has(e.id)) {
          relations.value.set(e.id, {
            id: e.id,
            source: e.source || '',
            target: e.target || '',
            relationType: e.relation_type || 'influence',
            weight: e.weight ?? 0.5,
            round: roundNumber ?? currentRound.value,
          })
        }
      }
    }

    // Update edges
    if (diff.updated_edges?.length) {
      for (const u of diff.updated_edges) {
        const existing = relations.value.get(u.id)
        if (existing) {
          if (u.weight !== undefined) existing.weight = u.weight
          if (u.relation_type !== undefined) existing.relationType = u.relation_type
        }
      }
    }

    // Trigger reactivity
    entities.value = new Map(entities.value)
    relations.value = new Map(relations.value)
  }

  function addAgentEntityLinks(links: Array<{ agent_id: string; entity_id: string }>) {
    for (const link of links) {
      const existing = agentEntityLinks.value.get(link.agent_id) || []
      if (!existing.includes(link.entity_id)) {
        existing.push(link.entity_id)
        agentEntityLinks.value.set(link.agent_id, existing)
      }
    }
    // Trigger reactivity
    agentEntityLinks.value = new Map(agentEntityLinks.value)
  }

  function getEntitiesForAgent(agentId: string): string[] {
    return agentEntityLinks.value.get(agentId) || []
  }

  function getAgentsForEntity(entityId: string): string[] {
    const agents: string[] = []
    for (const [agentId, entityIds] of agentEntityLinks.value) {
      if (entityIds.includes(entityId)) {
        agents.push(agentId)
      }
    }
    return agents
  }

  function setLayerVisible(visible: boolean) {
    layerVisible.value = visible
  }

  function toggleLayerVisible() {
    layerVisible.value = !layerVisible.value
  }

  function reset() {
    entities.value = new Map()
    relations.value = new Map()
    agentEntityLinks.value = new Map()
    layerVisible.value = false
    currentRound.value = -1
  }

  return {
    // State
    entities,
    relations,
    agentEntityLinks,
    layerVisible,
    currentRound,
    // Computed
    entityCount,
    relationCount,
    graphNodes,
    graphEdges,
    agentEntityEdges,
    // Actions
    applyDiff,
    addAgentEntityLinks,
    getEntitiesForAgent,
    getAgentsForEntity,
    setLayerVisible,
    toggleLayerVisible,
    reset,
  }
})
