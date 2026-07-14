import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import type { GraphActivityEvent, GraphStateResponse } from '../../api/client'
import { useSocialGraphActivityStore } from '../../stores/socialGraphActivityStore'
import { useSocialGraphTopologyStore } from '../../stores/socialGraphTopologyStore'
import SocialGraphWorkspace from '../SocialGraphWorkspace.vue'

const snapshot: GraphStateResponse = {
  simulation_id: 'sim-workspace',
  population_id: 'pop-1',
  nodes: [{
    id: 'agent-1',
    agent_index: 1,
    demographics: { age: 30, gender: '', occupation: '会社員', region: '関東', income_bracket: '', education: '' },
    big_five: {},
    values: {},
    speech_style: '',
    stance: '賛成',
    confidence: 0.8,
    reason: '地域の便益',
    concern: '',
    priority: '',
  }],
  edges: [],
  population_network: {
    population_id: 'pop-1',
    node_count: 1,
    edge_count: 0,
    nodes: [{ id: 'agent-1', agent_index: 1 }],
    edges: [],
  },
  current_phase: 'meeting',
  current_round: 1,
  latest_event_id: 1,
}

const dialogue: GraphActivityEvent = {
  id: 1,
  simulation_id: 'sim-workspace',
  occurred_at: '2026-07-13T00:00:00Z',
  phase: 'meeting',
  round: 1,
  kind: 'dialogue',
  source_id: 'agent-1',
  payload: { participant_name: '代表A', argument: '地域の便益を重視します' },
}

describe('SocialGraphWorkspace', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('synchronizes phase header, timeline selection, and node inspector', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const topology = useSocialGraphTopologyStore()
    topology.hydrate(snapshot)
    const activity = useSocialGraphActivityStore()
    activity.beginBuffering('sim-workspace')
    activity.hydrateHistory([dialogue], 1)
    activity.completeBuffering([], topology.applyEvent)

    const wrapper = mount(SocialGraphWorkspace, {
      props: {
        simulationId: 'sim-workspace',
        mode: 'replay',
        autoBootstrap: false,
      },
      global: {
        plugins: [pinia],
        stubs: {
          SigmaSocialGraph: {
            props: ['nodes', 'edges'],
            template: '<button data-testid="sigma" @click="$emit(\'select-node\', \'agent-1\')">graph</button>',
          },
        },
      },
    })

    await wrapper.get('[data-testid="sigma"]').trigger('click')
    expect(wrapper.get('[data-testid="phase-label"]').text()).toContain('meeting')
    expect(wrapper.get('[data-testid="node-inspector"]').text()).toContain('会社員')
    expect(wrapper.get('[data-testid="activity-timeline"]').text()).toContain('地域の便益')
  })

  it('detaches from live at an earlier event and can return to the tail', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const topology = useSocialGraphTopologyStore()
    topology.hydrate({ ...snapshot, latest_event_id: 2 })
    const activity = useSocialGraphActivityStore()
    const second = { ...dialogue, id: 2, payload: { argument: '二つ目' } }
    activity.beginBuffering('sim-workspace')
    activity.hydrateHistory([dialogue, second], 2)
    activity.completeBuffering([], topology.applyEvent)

    const wrapper = mount(SocialGraphWorkspace, {
      props: { simulationId: 'sim-workspace', mode: 'replay', autoBootstrap: false },
      global: {
        plugins: [pinia],
        stubs: { SigmaSocialGraph: { template: '<div />' } },
      },
    })

    await wrapper.get('[data-event-id="1"]').trigger('click')
    expect(wrapper.text()).toContain('Replay')
    await wrapper.get('[data-testid="return-live"]').trigger('click')
    expect(wrapper.text()).toContain('Live')
  })

  it('shows a readable graph summary and exploration hint during a live run', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useSocialGraphTopologyStore().hydrate(snapshot)

    const wrapper = mount(SocialGraphWorkspace, {
      props: { simulationId: 'sim-workspace', mode: 'live', autoBootstrap: false },
      global: {
        plugins: [pinia],
        stubs: { SigmaSocialGraph: { template: '<div data-testid="sigma" />' } },
      },
    })

    expect(wrapper.get('[data-testid="graph-context"]').text()).toContain('代表 1人')
    expect(wrapper.get('[data-testid="graph-context"]').text()).toContain('全体 1人')
    expect(wrapper.text()).toContain('検索またはノード選択で詳しく確認')
  })
})
