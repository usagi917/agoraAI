import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useKGEvolutionStore } from '../kgEvolutionStore'

describe('kgEvolutionStore replay', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('filters KG nodes and edges by replay round', () => {
    const store = useKGEvolutionStore()

    store.applyDiff({
      added_nodes: [
        { id: 'kg-policy', label: '政策', type: 'policy', importance_score: 0.8 },
      ],
      added_edges: [],
    }, 0)
    store.applyDiff({
      added_nodes: [
        { id: 'kg-market', label: '市場', type: 'market', importance_score: 0.6 },
      ],
      added_edges: [
        {
          id: 'kg-edge-policy-market',
          source: 'kg-policy',
          target: 'kg-market',
          relation_type: 'influence',
          weight: 0.7,
        },
      ],
    }, 1)

    expect(store.graphNodes.map(node => node.id)).toEqual(['kg-policy', 'kg-market'])
    expect(store.graphEdges.map(edge => edge.id)).toEqual(['kg-edge-policy-market'])

    store.setReplayRound(0)

    expect(store.graphNodes.map(node => node.id)).toEqual(['kg-policy'])
    expect(store.graphEdges).toEqual([])

    store.clearReplayRound()

    expect(store.graphNodes.map(node => node.id)).toEqual(['kg-policy', 'kg-market'])
    expect(store.graphEdges.map(edge => edge.id)).toEqual(['kg-edge-policy-market'])
  })

  it('filters agent-entity links to the visible replay window', () => {
    const store = useKGEvolutionStore()

    store.applyDiff({
      added_nodes: [
        { id: 'kg-policy', label: '政策', type: 'policy', importance_score: 0.8 },
      ],
      added_edges: [],
    }, 0)
    store.applyDiff({
      added_nodes: [
        { id: 'kg-market', label: '市場', type: 'market', importance_score: 0.6 },
      ],
      added_edges: [],
    }, 1)
    store.addAgentEntityLinks([
      { agent_id: 'agent-1', entity_id: 'kg-policy' },
      { agent_id: 'agent-1', entity_id: 'kg-market' },
    ])

    expect(store.agentEntityEdges.map(edge => edge.id)).toEqual([
      'link-agent-1-kg-policy',
      'link-agent-1-kg-market',
    ])

    store.setReplayRound(0)

    expect(store.agentEntityEdges.map(edge => edge.id)).toEqual([
      'link-agent-1-kg-policy',
    ])
  })
})
