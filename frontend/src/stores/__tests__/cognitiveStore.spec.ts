import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useCognitiveStore } from '../cognitiveStore'

describe('cognitiveStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('filters reflections by the selected agent source memories', () => {
    const store = useCognitiveStore()

    store.addMemoryEntry({
      id: 'm-agent-a',
      agentId: 'agent-a',
      memoryType: 'episodic',
      content: 'Agent A memory',
      importance: 0.7,
      round: 1,
      isReflection: false,
      reflectionLevel: 0,
    })
    store.addMemoryEntry({
      id: 'm-agent-b',
      agentId: 'agent-b',
      memoryType: 'episodic',
      content: 'Agent B memory',
      importance: 0.6,
      round: 1,
      isReflection: false,
      reflectionLevel: 0,
    })

    store.addReflection({
      insight: 'Agent A insight',
      importance: 0.9,
      level: 1,
      sourceIds: ['m-agent-a'],
      round: 1,
    })
    store.addReflection({
      insight: 'Agent B insight',
      importance: 0.5,
      level: 1,
      sourceIds: ['m-agent-b'],
      round: 1,
    })

    store.selectAgent('agent-a')

    expect(store.selectedAgentReflections.map(reflection => reflection.insight)).toEqual([
      'Agent A insight',
    ])
  })
})
