import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import AgentActivityTicker from '../AgentActivityTicker.vue'
import { useAgentVisualizationStore } from '../../stores/agentVisualizationStore'
import { useSimulationStore } from '../../stores/simulationStore'

describe('AgentActivityTicker', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders nothing when not running and no events', () => {
    const wrapper = mount(AgentActivityTicker)
    expect(wrapper.find('.ticker-container').exists()).toBe(false)
    expect(wrapper.findAll('.ticker-item').length).toBe(0)
  })

  it('shows waiting state when running but no events', () => {
    const simStore = useSimulationStore()
    simStore.setStatus('running')

    const wrapper = mount(AgentActivityTicker)
    expect(wrapper.find('.ticker-container').exists()).toBe(true)
    expect(wrapper.find('.ticker-waiting').exists()).toBe(true)
    expect(wrapper.text()).toContain('モニタリング中')
  })

  it('renders ticker items from recentThoughts', () => {
    const store = useAgentVisualizationStore()
    store.addRecentThought({
      agentId: 'a1',
      agentName: 'Agent Alpha',
      reasoningChain: 'analyzing market data',
      chosenAction: 'evaluate_risk',
      timestamp: Date.now(),
    })

    const wrapper = mount(AgentActivityTicker)
    const items = wrapper.findAll('.ticker-item')
    expect(items.length).toBe(1)
    expect(wrapper.text()).toContain('Agent Alpha')
    expect(wrapper.text()).toContain('evaluate_risk')
  })

  it('renders ticker items from communicationFlows', () => {
    const store = useAgentVisualizationStore()
    store.addCommunicationFlow({
      sourceId: 'agent-1',
      targetId: 'agent-2',
      messageType: 'conversation',
      content: 'discussing policy impact',
      timestamp: Date.now(),
    })

    const wrapper = mount(AgentActivityTicker)
    const items = wrapper.findAll('.ticker-item')
    expect(items.length).toBe(1)
    expect(wrapper.text()).toContain('discussing policy impact')
  })

  it('renders ticker items from dialogueEvents', () => {
    const store = useAgentVisualizationStore()
    store.addDialogueEvent({
      participantName: 'Expert X',
      argument: 'The regulation needs revision',
      round: 1,
    })

    const wrapper = mount(AgentActivityTicker)
    const items = wrapper.findAll('.ticker-item')
    expect(items.length).toBe(1)
    expect(wrapper.text()).toContain('Expert X')
  })

  it('shows at most 8 visible items', () => {
    const store = useAgentVisualizationStore()
    for (let i = 0; i < 15; i++) {
      store.addRecentThought({
        agentId: `a${i}`,
        agentName: `Agent${i}`,
        reasoningChain: `r${i}`,
        chosenAction: `act${i}`,
        timestamp: Date.now() + i,
      })
    }

    const wrapper = mount(AgentActivityTicker)
    const items = wrapper.findAll('.ticker-item')
    expect(items.length).toBeLessThanOrEqual(8)
  })

  it('toggles minimized state', async () => {
    const store = useAgentVisualizationStore()
    store.addRecentThought({
      agentId: 'a1',
      agentName: 'Agent1',
      reasoningChain: 'r1',
      chosenAction: 'act1',
      timestamp: Date.now(),
    })

    const wrapper = mount(AgentActivityTicker)
    expect(wrapper.find('.ticker-container').classes()).not.toContain('minimized')

    await wrapper.find('.ticker-toggle').trigger('click')
    expect(wrapper.find('.ticker-container').classes()).toContain('minimized')

    await wrapper.find('.ticker-toggle').trigger('click')
    expect(wrapper.find('.ticker-container').classes()).not.toContain('minimized')
  })

  it('applies correct type class to ticker items', () => {
    const store = useAgentVisualizationStore()
    store.addRecentThought({
      agentId: 'a1',
      agentName: 'Agent1',
      reasoningChain: 'r1',
      chosenAction: 'act1',
      timestamp: Date.now(),
    })
    store.addCommunicationFlow({
      sourceId: 'a1',
      targetId: 'a2',
      messageType: 'conversation',
      content: 'hello',
      timestamp: Date.now() + 1,
    })

    const wrapper = mount(AgentActivityTicker)
    const items = wrapper.findAll('.ticker-item')
    expect(items.some(item => item.classes().includes('type-thought'))).toBe(true)
    expect(items.some(item => item.classes().includes('type-communication'))).toBe(true)
  })
})
