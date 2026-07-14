import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import LiveSocietyGraph from '../LiveSocietyGraph.vue'
import { useKGEvolutionStore } from '../../stores/kgEvolutionStore'
import { useSimulationStore } from '../../stores/simulationStore'
import { useSocietyGraphStore } from '../../stores/societyGraphStore'

describe('LiveSocietyGraph', () => {
  const firePulseSpy = vi.fn()

  beforeEach(() => {
    vi.useFakeTimers()
    firePulseSpy.mockClear()
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
            setup(_props: unknown, { expose }: { expose: (exposed: Record<string, unknown>) => void }) {
              expose({ firePulse: firePulseSpy })
            },
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

  it('uses visible layer labels', () => {
    const wrapper = mountGraph()

    expect(wrapper.text()).toContain('社会')
    expect(wrapper.text()).toContain('知識')
    expect(wrapper.text()).toContain('リンク')
  })

  it('shows the configured default population size during society pulse startup', () => {
    const simulationStore = useSimulationStore()
    simulationStore.setMode('standard')
    simulationStore.setUnifiedPhase('society_pulse')
    useSocietyGraphStore().reset()

    const wrapper = mountGraph()

    expect(wrapper.get('.empty-title').text()).toBe('10,000人の社会反応を測定しています')
  })

  it('fires a synapse pulse when a new addressed dialogue arrives', async () => {
    const societyGraphStore = useSocietyGraphStore()
    societyGraphStore.setSelectedAgents([
      { id: 'agent-1', agent_index: 1, name: '田中', display_name: '田中', occupation: '会社員', age: 35, region: '東京' },
      { id: 'agent-2', agent_index: 2, name: '佐藤', display_name: '佐藤', occupation: '医師', age: 42, region: '大阪' },
    ])

    mountGraph()
    await nextTick()

    societyGraphStore.appendMeetingDialogue(1, {
      participant_name: '田中',
      participant_index: 1,
      role: 'citizen',
      argument: '賛成です',
      addressed_to_participant_index: 2,
    })
    await nextTick()

    expect(firePulseSpy).toHaveBeenCalledWith('agent-1', 'agent-2')
  })

  it('does not re-fire the same dialogue on repeated store updates', async () => {
    const societyGraphStore = useSocietyGraphStore()
    societyGraphStore.setSelectedAgents([
      { id: 'agent-1', agent_index: 1, name: '田中', display_name: '田中', occupation: '会社員', age: 35, region: '東京' },
      { id: 'agent-2', agent_index: 2, name: '佐藤', display_name: '佐藤', occupation: '医師', age: 42, region: '大阪' },
    ])

    mountGraph()
    await nextTick()

    societyGraphStore.appendMeetingDialogue(1, {
      participant_name: '田中',
      participant_index: 1,
      role: 'citizen',
      argument: '賛成です',
      addressed_to_participant_index: 2,
    })
    await nextTick()
    // A second, unrelated speaker update must not replay the first pulse.
    societyGraphStore.appendMeetingDialogue(1, {
      participant_name: '佐藤',
      participant_index: 2,
      role: 'citizen',
      argument: '私も同意します',
      addressed_to_participant_index: 1,
    })
    await nextTick()

    expect(firePulseSpy).toHaveBeenCalledTimes(2)
    expect(firePulseSpy).toHaveBeenNthCalledWith(1, 'agent-1', 'agent-2')
    expect(firePulseSpy).toHaveBeenNthCalledWith(2, 'agent-2', 'agent-1')
  })
})
