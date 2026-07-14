import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import type { GraphActivityEvent, GraphStateResponse } from '../../api/client'
import { useSocialGraphTopologyStore } from '../socialGraphTopologyStore'

const snapshot: GraphStateResponse = {
  simulation_id: 'sim-1',
  population_id: 'pop-1',
  nodes: [{
    id: 'agent-1',
    agent_index: 1,
    demographics: { age: 30, gender: '', occupation: '会社員', region: '関東', income_bracket: '', education: '' },
    big_five: {},
    values: {},
    speech_style: '',
    stance: '中立',
    confidence: 0.5,
    reason: '',
    concern: '',
    priority: '',
  }],
  edges: [{
    id: 'edge-1',
    source: 'agent-1',
    target: 'agent-2',
    relation_type: 'friend',
    strength: 0.4,
  }],
  population_network: {
    population_id: 'pop-1',
    node_count: 2,
    edge_count: 1,
    nodes: [{ id: 'agent-1', agent_index: 1 }, { id: 'agent-2', agent_index: 2 }],
    edges: [[1, 2, 0.4]],
  },
  current_phase: 'activation',
  current_round: 0,
  latest_event_id: 10,
}

function graphEvent(overrides: Partial<GraphActivityEvent>): GraphActivityEvent {
  return {
    id: 11,
    simulation_id: 'sim-1',
    occurred_at: '2026-07-13T00:00:00Z',
    phase: 'meeting',
    round: 1,
    kind: 'dialogue',
    payload: {},
    ...overrides,
  }
}

describe('socialGraphTopologyStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('hydrates representative and compact population layers', () => {
    const store = useSocialGraphTopologyStore()
    store.hydrate(snapshot)

    expect(store.nodes.get('agent-1')?.stance).toBe('中立')
    expect(store.nodes.get('agent-1')?.role).toBe('activated')
    expect(store.populationNetwork?.node_count).toBe(2)
    expect(store.snapshotCursor).toBe(10)
  })

  it('applies stance and relationship changes idempotently', () => {
    const store = useSocialGraphTopologyStore()
    store.hydrate(snapshot)

    store.applyEvent(graphEvent({
      id: 11,
      kind: 'stance_shift',
      source_id: 'agent-1',
      payload: { before_stance: '中立', after_stance: '賛成' },
    }))
    store.applyEvent(graphEvent({
      id: 12,
      kind: 'relationship_changed',
      source_id: 'agent-1',
      target_id: 'agent-2',
      edge_id: 'edge-1',
      payload: {
        relation_type: 'friend',
        before_strength: 0.4,
        after_strength: 0.7,
        delta: 0.3,
        is_new: false,
      },
    }))
    store.applyEvent(graphEvent({
      id: 12,
      kind: 'relationship_changed',
      edge_id: 'edge-1',
      payload: { after_strength: 0.7 },
    }))

    expect(store.nodes.get('agent-1')?.stance).toBe('賛成')
    expect(store.edges.get('edge-1')?.strength).toBe(0.7)
    expect(store.lastAppliedEventId).toBe(12)
  })
})
