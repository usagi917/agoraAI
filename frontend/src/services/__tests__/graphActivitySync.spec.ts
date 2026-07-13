import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { GraphActivityEvent, GraphStateResponse } from '../../api/client'
import { useSocialGraphActivityStore } from '../../stores/socialGraphActivityStore'
import { useSocietyGraphStore } from '../../stores/societyGraphStore'
import { bootstrapGraphActivity } from '../graphActivitySync'

const apiMocks = vi.hoisted(() => ({
  getGraphEvents: vi.fn(),
  getGraphState: vi.fn(),
}))

vi.mock('../../api/client', () => apiMocks)

const snapshot: GraphStateResponse = {
  simulation_id: 'sim-buffered',
  population_id: 'pop-buffered',
  nodes: [],
  edges: [],
  population_network: {
    population_id: 'pop-buffered',
    node_count: 0,
    edge_count: 0,
    nodes: [],
    edges: [],
  },
  current_phase: 'meeting',
  current_round: 1,
  latest_event_id: 1,
}

const bufferedEvent: GraphActivityEvent = {
  id: 2,
  simulation_id: 'sim-buffered',
  occurred_at: '2026-07-13T00:00:02Z',
  phase: 'relationship_evolution',
  round: 3,
  kind: 'relationship_changed',
  source_id: 'agent-1',
  target_id: 'agent-2',
  edge_id: 'edge-1',
  payload: {
    relation_type: 'friend',
    after_strength: 0.75,
  },
}

describe('bootstrapGraphActivity', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMocks.getGraphState.mockReset().mockResolvedValue(snapshot)
    apiMocks.getGraphEvents.mockReset().mockResolvedValue([])
  })

  it('applies an SSE event buffered during bootstrap to the legacy graph store', async () => {
    const activity = useSocialGraphActivityStore()
    const legacy = useSocietyGraphStore()
    const applyLegacy = vi.spyOn(legacy, 'applyGraphActivityEvent')
    activity.beginBuffering('sim-buffered')
    activity.receive(bufferedEvent, vi.fn())

    await bootstrapGraphActivity('sim-buffered', { bufferingStarted: true })

    expect(applyLegacy).toHaveBeenCalledWith(bufferedEvent)
  })
})
