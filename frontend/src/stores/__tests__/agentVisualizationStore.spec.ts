import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgentVisualizationStore } from '../agentVisualizationStore'

describe('agentVisualizationStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  it('setThinkingAgent sets and auto-clears after timeout', () => {
    const store = useAgentVisualizationStore()

    store.setThinkingAgent('agent-1')
    expect(store.thinkingAgentId).toBe('agent-1')
    expect(store.agentStatusMap['agent-1']).toBe('thinking')

    vi.advanceTimersByTime(30_000)
    expect(store.thinkingAgentId).toBeNull()
    expect(store.agentStatusMap['agent-1']).toBe('idle')
  })

  it('clearThinkingAgent clears immediately', () => {
    const store = useAgentVisualizationStore()

    store.setThinkingAgent('agent-1')
    store.clearThinkingAgent('agent-1')
    expect(store.thinkingAgentId).toBeNull()
  })

  it('agentStatusMap reflects thinking state', () => {
    const store = useAgentVisualizationStore()

    expect(store.getAgentStatus('unknown-agent')).toBe('idle')

    store.setThinkingAgent('agent-1')
    expect(store.getAgentStatus('agent-1')).toBe('thinking')
  })

  it('addRecentThought maintains max limit', () => {
    const store = useAgentVisualizationStore()

    for (let i = 0; i < 25; i++) {
      store.addRecentThought({
        agentId: `agent-${i}`,
        agentName: `Agent ${i}`,
        reasoningChain: `reasoning ${i}`,
        chosenAction: `action ${i}`,
        timestamp: Date.now() + i,
      })
    }

    expect(store.recentThoughts.length).toBeLessThanOrEqual(20)
  })

  it('latestThought returns the most recent', () => {
    const store = useAgentVisualizationStore()

    store.addRecentThought({
      agentId: 'a1',
      agentName: 'First',
      reasoningChain: 'first',
      chosenAction: 'first',
      timestamp: 100,
    })
    store.addRecentThought({
      agentId: 'a2',
      agentName: 'Second',
      reasoningChain: 'second',
      chosenAction: 'second',
      timestamp: 200,
    })

    expect(store.latestThought?.agentName).toBe('Second')
  })

  it('addCommunicationFlow tracks edges', () => {
    const store = useAgentVisualizationStore()

    store.addCommunicationFlow({
      sourceId: 'a1',
      targetId: 'a2',
      messageType: 'say',
      content: 'hello',
      timestamp: Date.now(),
    })

    expect(store.communicationFlows.length).toBe(1)
    expect(store.communicationFlows[0].sourceId).toBe('a1')
  })

  it('addCommunicationFlow maintains max limit', () => {
    const store = useAgentVisualizationStore()

    for (let i = 0; i < 60; i++) {
      store.addCommunicationFlow({
        sourceId: `a${i}`,
        targetId: `b${i}`,
        messageType: 'say',
        content: `msg ${i}`,
        timestamp: Date.now() + i,
      })
    }

    expect(store.communicationFlows.length).toBeLessThanOrEqual(50)
  })

  it('setAgentStatus sets and gets correctly', () => {
    const store = useAgentVisualizationStore()

    store.setAgentStatus('agent-1', 'executing')
    expect(store.getAgentStatus('agent-1')).toBe('executing')

    store.setAgentStatus('agent-1', 'debating')
    expect(store.getAgentStatus('agent-1')).toBe('debating')
  })

  it('reset clears all state', () => {
    const store = useAgentVisualizationStore()

    store.setThinkingAgent('agent-1')
    store.addRecentThought({
      agentId: 'a1',
      agentName: 'A',
      reasoningChain: 'r',
      chosenAction: 'a',
      timestamp: 1,
    })
    store.addCommunicationFlow({
      sourceId: 'a1',
      targetId: 'a2',
      messageType: 'say',
      content: 'hi',
      timestamp: 1,
    })

    store.reset()

    expect(store.thinkingAgentId).toBeNull()
    expect(store.recentThoughts.length).toBe(0)
    expect(store.communicationFlows.length).toBe(0)
  })

  describe('tickerEvents', () => {
    it('merges thoughts and communication flows sorted by timestamp', () => {
      const store = useAgentVisualizationStore()

      store.addRecentThought({
        agentId: 'a1',
        agentName: 'Agent1',
        reasoningChain: 'thinking about X',
        chosenAction: 'act_x',
        timestamp: 200,
      })
      store.addCommunicationFlow({
        sourceId: 'a1',
        targetId: 'a2',
        messageType: 'conversation',
        content: 'hello a2',
        timestamp: 100,
      })

      const events = store.tickerEvents
      expect(events.length).toBe(2)
      // sorted by timestamp ascending
      expect(events[0].type).toBe('communication')
      expect(events[0].timestamp).toBe(100)
      expect(events[1].type).toBe('thought')
      expect(events[1].timestamp).toBe(200)
    })

    it('includes dialogue events', () => {
      const store = useAgentVisualizationStore()

      store.addDialogueEvent({
        participantName: 'Expert A',
        argument: 'We should consider the impact',
        round: 1,
      })

      const events = store.tickerEvents
      expect(events.length).toBe(1)
      expect(events[0].type).toBe('dialogue')
      expect(events[0].agentName).toBe('Expert A')
      expect(events[0].summary).toContain('We should consider')
    })

    it('caps ticker events at the last 30', () => {
      const store = useAgentVisualizationStore()

      for (let i = 0; i < 20; i++) {
        store.addRecentThought({
          agentId: `a${i}`,
          agentName: `Agent${i}`,
          reasoningChain: `r${i}`,
          chosenAction: `act${i}`,
          timestamp: i,
        })
      }
      for (let i = 0; i < 20; i++) {
        store.addCommunicationFlow({
          sourceId: `a${i}`,
          targetId: `b${i}`,
          messageType: 'say',
          content: `msg${i}`,
          timestamp: 100 + i,
        })
      }

      expect(store.tickerEvents.length).toBeLessThanOrEqual(30)
    })
  })

  describe('addDialogueEvent', () => {
    it('adds a dialogue event to dialogueEvents', () => {
      const store = useAgentVisualizationStore()

      store.addDialogueEvent({
        participantName: 'Citizen B',
        argument: 'I disagree because...',
        round: 2,
      })

      expect(store.dialogueEvents.length).toBe(1)
      expect(store.dialogueEvents[0].participantName).toBe('Citizen B')
    })

    it('maintains max limit for dialogueEvents', () => {
      const store = useAgentVisualizationStore()

      for (let i = 0; i < 35; i++) {
        store.addDialogueEvent({
          participantName: `Speaker${i}`,
          argument: `arg ${i}`,
          round: 1,
        })
      }

      expect(store.dialogueEvents.length).toBeLessThanOrEqual(30)
    })

    it('reset clears dialogueEvents', () => {
      const store = useAgentVisualizationStore()

      store.addDialogueEvent({
        participantName: 'X',
        argument: 'Y',
        round: 1,
      })
      store.reset()

      expect(store.dialogueEvents.length).toBe(0)
    })
  })
})
