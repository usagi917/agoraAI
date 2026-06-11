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

  it('uses canonical id from SSE payload when available', () => {
    const store = useSocietyGraphStore()

    store.setSelectedAgents([
      {
        id: 'backend-uuid-1',
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

    // Agent with id from backend uses it; agent without falls back to agent-{index}
    expect(store.liveAgents.get('backend-uuid-1')).toBeDefined()
    expect(store.liveAgents.get('backend-uuid-1')?.agentIndex).toBe(1)
    expect(store.liveAgents.get('agent-2')).toBeDefined()
    expect(store.liveAgents.get('agent-2')?.agentIndex).toBe(2)
    // Ensure fallback key is NOT used when backend id is present
    expect(store.liveAgents.get('agent-1')).toBeUndefined()
  })

  it('deduplicates streamed meeting dialogue and clears the active speaker after round completion', () => {
    const store = useSocietyGraphStore()

    store.setSelectedAgents([
      {
        id: 'agent-1',
        agent_index: 1,
        name: '田中太郎',
        display_name: '田中太郎',
        occupation: '会社員',
        age: 35,
        region: '東京',
      },
      {
        id: 'agent-2',
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
        id: 'agent-1',
        agent_index: 1,
        name: '田中太郎',
        display_name: '田中太郎',
        occupation: '会社員',
        age: 35,
        region: '東京',
      },
      {
        id: 'agent-2',
        agent_index: 2,
        name: '佐藤花子',
        display_name: '佐藤花子',
        occupation: '経営者',
        age: 42,
        region: '大阪',
      },
      {
        id: 'agent-3',
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

describe('societyGraphStore: 人口レイヤー（全人口伝播）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  function seedPopulation(store: ReturnType<typeof useSocietyGraphStore>) {
    store.setSelectedAgents([
      { id: 'sel-0', agent_index: 0, name: 'A0', occupation: '会社員', age: 30, region: '関東' },
    ])
    store.setPopulationNetwork({
      population_id: 'pop-1',
      node_count: 4,
      edge_count: 2,
      nodes: [
        { id: 'sel-0', agent_index: 0 },
        { id: 'pop-1-a', agent_index: 1 },
        { id: 'pop-2-a', agent_index: 2 },
        { id: 'pop-3-a', agent_index: 3 },
      ],
      edges: [
        [0, 1, 0.8],
        [2, 3, 0.4],
      ],
    })
  }

  it('setPopulationNetwork が人口ノード/エッジを graphNodes/graphEdges に合流させる', () => {
    const store = useSocietyGraphStore()
    seedPopulation(store)

    expect(store.populationNodeCount).toBe(4)

    const ids = store.graphNodes.map((n) => n.id)
    // 選抜済み sel-0 は重複しない（liveAgents 側が優先）
    expect(ids.filter((id) => id === 'sel-0')).toHaveLength(1)
    expect(ids).toContain('pop-1-a')
    expect(ids).toContain('pop-3-a')

    const popNode = store.graphNodes.find((n) => n.id === 'pop-1-a')
    expect(popNode?.tier).toBe('population')

    const popEdges = store.graphEdges.filter((e) => e.id?.startsWith('pop-edge-'))
    expect(popEdges).toHaveLength(2)
    expect(popEdges[0].source).toBe('sel-0')
    expect(popEdges[0].target).toBe('pop-1-a')
    expect(popEdges[0].weight).toBe(0.8)
  })

  it('applyPropagationRound がスタンスの波をノード色に反映する', () => {
    const store = useSocietyGraphStore()
    seedPopulation(store)

    store.applyPropagationRound([
      { i: 1, s: '条件付き賛成' },
      { i: 0, s: '賛成' },
    ])

    const popNode = store.graphNodes.find((n) => n.id === 'pop-1-a')
    expect(popNode?.stance).toBe('条件付き賛成')
    // 未変化ノードは中立のまま
    const untouched = store.graphNodes.find((n) => n.id === 'pop-2-a')
    expect(untouched?.stance ?? '').toBe('')
    // 選抜済みエージェントは liveAgents 側のスタンスが更新される
    expect(store.liveAgents.get('sel-0')?.stance).toBe('賛成')
  })

  it('populationVisible=false で人口レイヤーが消える', () => {
    const store = useSocietyGraphStore()
    seedPopulation(store)

    store.populationVisible = false

    expect(store.graphNodes.some((n) => n.tier === 'population')).toBe(false)
    expect(store.graphEdges.some((e) => e.id?.startsWith('pop-edge-'))).toBe(false)
  })

  it('reset が人口レイヤーを初期化する', () => {
    const store = useSocietyGraphStore()
    seedPopulation(store)
    store.applyPropagationRound([{ i: 1, s: '賛成' }])

    store.reset()

    expect(store.populationNodeCount).toBe(0)
    expect(store.graphNodes).toHaveLength(0)
  })
})
