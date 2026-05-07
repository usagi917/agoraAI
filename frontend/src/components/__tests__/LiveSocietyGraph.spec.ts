import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LiveSocietyGraph from '../LiveSocietyGraph.vue'
import { useKGEvolutionStore } from '../../stores/kgEvolutionStore'
import { useSimulationStore } from '../../stores/simulationStore'
import { useSocietyGraphStore } from '../../stores/societyGraphStore'

describe('LiveSocietyGraph', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())

    const simulationStore = useSimulationStore()
    simulationStore.setStatus('completed')
    simulationStore.setSocietyPhase('completed')

    const societyGraphStore = useSocietyGraphStore()
    societyGraphStore.setSelectedAgents([
      {
        id: 'agent-1',
        agent_index: 1,
        name: '田中太郎',
        display_name: '田中太郎',
        occupation: '会社員',
        age: 35,
        region: '東京',
      },
    ])

    const kgStore = useKGEvolutionStore()
    kgStore.applyDiff({
      added_nodes: [
        { id: 'kg-policy', label: '政策', type: 'policy', importance_score: 0.8 },
      ],
      added_edges: [],
    }, 0)
    kgStore.applyDiff({
      added_nodes: [
        { id: 'kg-market', label: '市場', type: 'market', importance_score: 0.6 },
      ],
      added_edges: [],
    }, 1)
    kgStore.setLayerVisible(true)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function mountGraph() {
    return mount(LiveSocietyGraph, {
      props: {
        simulationId: 'sim-1',
      },
      global: {
        stubs: {
          ForceGraph2D: {
            props: ['highlightedNodeIds'],
            emits: ['select-node'],
            template: `
              <div data-testid="graph-2d">
                <button data-testid="select-kg-node" @click="$emit('select-node', { id: 'kg-policy' })" />
                <span data-testid="highlighted-node-ids">{{ highlightedNodeIds.join(',') }}</span>
              </div>
            `,
          },
          ConversationToast: true,
          NodeDetailPanel: {
            emits: ['highlight-agents', 'close', 'select-agent'],
            template: '<button data-testid="highlight-agents" @click="$emit(\'highlight-agents\', [\'agent-1\'])">Highlight</button>',
          },
        },
      },
    })
  }

  it('updates the KG replay round when the scrubber moves', async () => {
    const wrapper = mountGraph()
    const kgStore = useKGEvolutionStore()

    const slider = wrapper.get('input[type="range"]')
    expect((slider.element as HTMLInputElement).value).toBe('1')
    expect((slider.element as HTMLInputElement).max).toBe('1')

    await slider.setValue('0')

    expect(kgStore.replayRound).toBe(0)
  })

  it('advances replay rounds while playback is active and stops at the end', async () => {
    const wrapper = mountGraph()
    const kgStore = useKGEvolutionStore()

    await wrapper.get('input[type="range"]').setValue('0')
    await wrapper.get('.play-btn').trigger('click')

    vi.advanceTimersByTime(1000)
    await nextTick()

    expect(kgStore.replayRound).toBe(1)
    expect(wrapper.get('.play-btn').text()).toBe('▶')
  })

  it('passes related KG agents to the 2D graph highlight state', async () => {
    const wrapper = mountGraph()

    await wrapper.get('[data-testid="select-kg-node"]').trigger('click')
    await wrapper.get('[data-testid="highlight-agents"]').trigger('click')

    expect(wrapper.get('[data-testid="highlighted-node-ids"]').text()).toBe('agent-1')
  })
})
