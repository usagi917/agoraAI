import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useSocietyGraphStore, type MeetingArgument } from '../societyGraphStore'

function createArgument(overrides: Partial<MeetingArgument> = {}): MeetingArgument {
  return {
    participant_name: '田中太郎',
    participant_index: 1,
    role: 'citizen_representative',
    round: 2,
    argument: '段階的に進めるべきです。',
    questions_to_others: [],
    ...overrides,
  }
}

describe('societyGraphStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('deduplicates streamed meeting dialogue and clears the active speaker after round completion', () => {
    const store = useSocietyGraphStore()

    store.setSelectedAgents([
      {
        agent_index: 1,
        name: '田中太郎',
        display_name: '田中太郎',
        occupation: '会社員',
        age: 35,
        region: '東京',
      },
      {
        agent_index: 2,
        name: '佐藤花子',
        display_name: '佐藤花子',
        occupation: '経営者',
        age: 42,
        region: '大阪',
      },
    ])

    const argument = createArgument({
      addressed_to: '佐藤花子',
      addressed_to_participant_index: 2,
      sub_round: 'direct_exchange',
    })

    store.appendMeetingDialogue(2, argument)
    store.appendMeetingDialogue(2, argument)

    expect(store.currentRound).toBe(2)
    expect(store.currentArguments).toHaveLength(1)
    expect(store.speakingAgents.map((agent) => agent.id)).toEqual(['agent-1'])
    expect(store.conversationEdges).toEqual([
      {
        id: 'conv-2-agent-1-agent-2-direct_exchange',
        source: 'agent-1',
        target: 'agent-2',
        type: 'response',
        round: 2,
        intensity: 1,
      },
    ])

    store.completeMeetingRound(2, [argument])

    expect(store.currentArguments).toHaveLength(1)
    expect(store.speakingAgents).toEqual([])
    expect(store.liveAgents.get('agent-1')?.status).toBe('selected')
  })

  it('uses explicit response targets instead of creating implicit broadcast edges', () => {
    const store = useSocietyGraphStore()

    store.setSelectedAgents([
      {
        agent_index: 1,
        name: '田中太郎',
        display_name: '田中太郎',
        occupation: '会社員',
        age: 35,
        region: '東京',
      },
      {
        agent_index: 2,
        name: '佐藤花子',
        display_name: '佐藤花子',
        occupation: '経営者',
        age: 42,
        region: '大阪',
      },
      {
        agent_index: 3,
        name: '鈴木一郎',
        display_name: '鈴木一郎',
        occupation: '研究者',
        age: 50,
        region: '福岡',
      },
    ])

    store.setMeetingRound(2, [
      createArgument({
        addressed_to: '佐藤花子',
        addressed_to_participant_index: 2,
      }),
      createArgument({
        participant_name: '佐藤花子',
        participant_index: 2,
        argument: '財源の議論が必要です。',
        addressed_to: '田中太郎',
        addressed_to_participant_index: 1,
      }),
    ])

    expect(store.conversationEdges).toEqual([
      {
        id: 'conv-2-agent-1-agent-2-reply',
        source: 'agent-1',
        target: 'agent-2',
        type: 'response',
        round: 2,
        intensity: 0.9,
      },
      {
        id: 'conv-2-agent-2-agent-1-reply',
        source: 'agent-2',
        target: 'agent-1',
        type: 'response',
        round: 2,
        intensity: 0.9,
      },
    ])
  })
})
