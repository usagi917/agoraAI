import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  POPULATION_EDGE_DISPLAY_CAP,
  useSocietyGraphStore,
  type MeetingArgument,
} from '../societyGraphStore'
import { useKGEvolutionStore } from '../kgEvolutionStore'

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

  it('sets social edges early without mutating agent stance or status', () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'a1', agent_index: 1, name: 'A', occupation: '会社員', age: 30, region: '東京' },
      { id: 'a2', agent_index: 2, name: 'B', occupation: '医師', age: 40, region: '大阪' },
    ])

    store.setSocialEdges([
      { id: 'e1', source: 'a1', target: 'a2', relation_type: 'friend', strength: 0.8 },
      { id: 'e-weak', source: 'a1', target: 'a2', relation_type: 'acquaintance', strength: 0.2 },
    ])

    // 弱い関係も含め、すべての social edge が graphEdges に描画される
    const socialEdges = store.graphEdges.filter((e) => e.id === 'e1' || e.id === 'e-weak')
    expect(socialEdges.map((e) => e.id)).toEqual(['e1', 'e-weak'])
    expect(socialEdges[0].relation_type).toBe('friend')

    // 意見未確定の窓を壊さない: agent の stance/status は選抜直後のまま
    expect(store.liveAgents.get('a1')?.stance).toBeNull()
    expect(store.liveAgents.get('a1')?.status).toBe('selected')
    const node = store.graphNodes.find((n) => n.id === 'a1')
    expect(node?.stance).toBe('')
    expect(node?.status).toBe('selected')
  })

  it('sizes selected display-name agents from confidence instead of display-name presence', () => {
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
    ])

    const node = store.graphNodes.find((n) => n.id === 'agent-1')
    expect(node?.importance_score).toBe(0.5)
  })

  it('keeps confidence-based sizing identical before and after social graph hydration', () => {
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
    ])

    const immediateImportance = store.graphNodes.find((n) => n.id === 'agent-1')?.importance_score

    store.hydrateWithSocialGraph([
      {
        id: 'agent-1',
        agent_index: 1,
        demographics: {
          age: 35,
          gender: 'male',
          occupation: '会社員',
          region: '東京',
          income_bracket: 'middle',
          education: 'university',
        },
        big_five: {},
        values: {},
        speech_style: 'calm',
        stance: '賛成',
        confidence: 0.5,
        reason: 'テスト理由',
        concern: 'テスト懸念',
        priority: '生活',
      },
    ], [])

    const hydratedImportance = store.graphNodes.find((n) => n.id === 'agent-1')?.importance_score
    expect(immediateImportance).toBe(0.5)
    expect(hydratedImportance).toBe(0.5)
    expect(hydratedImportance).toBe(immediateImportance)
  })

  it('keeps KG layer nodes and edges hidden until the KG layer is explicitly visible', () => {
    const store = useSocietyGraphStore()
    const kgStore = useKGEvolutionStore()

    kgStore.applyDiff({
      added_nodes: [
        { id: 'kg-policy', label: '政策', type: 'concept', importance_score: 0.8 },
        { id: 'kg-budget', label: '予算', type: 'concept', importance_score: 0.6 },
      ],
      added_edges: [
        {
          id: 'kg-edge-policy-budget',
          source: 'kg-policy',
          target: 'kg-budget',
          relation_type: 'requires',
          weight: 0.7,
        },
      ],
    }, 0)

    expect(kgStore.layerVisible).toBe(false)
    expect(store.graphNodes.some((n) => n.id.startsWith('kg-'))).toBe(false)
    expect(store.graphEdges.some((e) => e.id?.startsWith('kg-'))).toBe(false)

    kgStore.setLayerVisible(true)

    expect(store.graphNodes.map((n) => n.id)).toEqual(expect.arrayContaining(['kg-policy', 'kg-budget']))
    expect(store.graphEdges.map((e) => e.id)).toContain('kg-edge-policy-budget')
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

  describe('feedEntries (cumulative live feed buffer)', () => {
    it('accumulates dialogue entries with speaker fields', () => {
      const store = useSocietyGraphStore()

      store.appendMeetingDialogue(1, createArgument({
        round: 1,
        argument: '最初の発言です。',
        position: '賛成',
        addressed_to: '佐藤花子',
      }))

      const dialogues = store.feedEntries.filter((e) => e.kind === 'dialogue')
      expect(dialogues).toHaveLength(1)
      expect(dialogues[0].participant_name).toBe('田中太郎')
      expect(dialogues[0].argument).toBe('最初の発言です。')
      expect(dialogues[0].position).toBe('賛成')
      expect(dialogues[0].addressed_to).toBe('佐藤花子')
      expect(dialogues[0].round).toBe(1)
      expect(typeof dialogues[0].receivedAt).toBe('number')
    })

    it('retains feed entries across round changes and inserts a round marker', () => {
      const store = useSocietyGraphStore()

      store.appendMeetingDialogue(1, createArgument({ round: 1, argument: 'round1' }))
      store.appendMeetingDialogue(2, createArgument({
        round: 2,
        round_name: '深掘り',
        argument: 'round2',
      }))

      // currentArguments only ever holds the current round
      expect(store.currentArguments).toHaveLength(1)

      // feed retains dialogue from BOTH rounds (unlike currentArguments)
      const dialogues = store.feedEntries.filter((e) => e.kind === 'dialogue')
      expect(dialogues).toHaveLength(2)
      expect(dialogues.map((d) => d.argument)).toEqual(['round1', 'round2'])

      // a round marker was inserted when the round switched to 2
      const roundMarkers = store.feedEntries.filter((e) => e.kind === 'round')
      const round2Marker = roundMarkers.find((r) => r.round === 2)
      expect(round2Marker).toBeDefined()
      expect(round2Marker?.round_name).toBe('深掘り')
    })

    it('appends stance_shift entries', () => {
      const store = useSocietyGraphStore()

      store.addStanceShifts([
        { participant: '田中太郎', from: '中立', to: '賛成', reason: '議論で納得した' },
      ])

      const shifts = store.feedEntries.filter((e) => e.kind === 'stance_shift')
      expect(shifts).toHaveLength(1)
      expect(shifts[0].participant).toBe('田中太郎')
      expect(shifts[0].from).toBe('中立')
      expect(shifts[0].to).toBe('賛成')
      expect(shifts[0].reason).toBe('議論で納得した')
    })

    it('does not add a duplicate dialogue entry', () => {
      const store = useSocietyGraphStore()

      const argument = createArgument({ round: 1, argument: '重複する発言' })
      store.appendMeetingDialogue(1, argument)
      store.appendMeetingDialogue(1, argument)

      const dialogues = store.feedEntries.filter((e) => e.kind === 'dialogue')
      expect(dialogues).toHaveLength(1)
    })

    it('caps the feed at 300 entries, dropping the oldest', () => {
      const store = useSocietyGraphStore()

      for (let i = 0; i < 350; i++) {
        store.appendMeetingDialogue(1, createArgument({ round: 1, argument: `msg-${i}` }))
      }

      expect(store.feedEntries).toHaveLength(300)
      const last = store.feedEntries[store.feedEntries.length - 1]
      expect(last.kind).toBe('dialogue')
      expect(last.argument).toBe('msg-349')
    })

    it('clears feed entries on reset', () => {
      const store = useSocietyGraphStore()

      store.appendMeetingDialogue(1, createArgument({ round: 1, argument: 'x' }))
      expect(store.feedEntries.length).toBeGreaterThan(0)

      store.reset()
      expect(store.feedEntries).toHaveLength(0)
    })

    it('records dialogue into the feed from completeMeetingRound alone (SSE gap fill)', () => {
      const store = useSocietyGraphStore()

      store.completeMeetingRound(2, [
        createArgument({ round: 2, round_name: '深掘り', argument: 'bulk発言A' }),
        createArgument({ round: 2, participant_index: 2, participant_name: '佐藤花子', argument: 'bulk発言B' }),
      ])

      const dialogues = store.feedEntries.filter((e) => e.kind === 'dialogue')
      expect(dialogues.map((d) => d.argument)).toEqual(['bulk発言A', 'bulk発言B'])
      // a round marker for round 2 is present via this path
      expect(store.feedEntries.some((e) => e.kind === 'round' && e.round === 2)).toBe(true)
    })

    it('records dialogue into the feed from setMeetingRound', () => {
      const store = useSocietyGraphStore()

      store.setMeetingRound(1, [createArgument({ round: 1, argument: 'batch発言' })])

      const dialogues = store.feedEntries.filter((e) => e.kind === 'dialogue')
      expect(dialogues).toHaveLength(1)
      expect(dialogues[0].argument).toBe('batch発言')
    })

    it('does not duplicate a streamed dialogue when completeMeetingRound repeats it', () => {
      const store = useSocietyGraphStore()

      const arg = createArgument({ round: 2, argument: '同一発言' })
      store.appendMeetingDialogue(2, arg)
      store.completeMeetingRound(2, [arg])

      const dialogues = store.feedEntries.filter((e) => e.kind === 'dialogue')
      expect(dialogues).toHaveLength(1)
    })

    it('does not duplicate stance_shift entries when the same shifts are re-sent', () => {
      const store = useSocietyGraphStore()

      const shifts = [{ participant: '田中太郎', from: '中立', to: '賛成', reason: '議論の結果' }]
      store.addStanceShifts(shifts)
      store.addStanceShifts(shifts)

      const stanceShifts = store.feedEntries.filter((e) => e.kind === 'stance_shift')
      expect(stanceShifts).toHaveLength(1)
    })
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

  it('発話ステータス更新では populationDisplayNodes の配列参照を作り直さない', () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'agent-0', agent_index: 0, name: 'A0', occupation: '会社員', age: 30, region: '関東' },
      { id: 'agent-1', agent_index: 1, name: 'A1', occupation: '経営者', age: 40, region: '関西' },
    ])
    store.setPopulationNetwork({
      population_id: 'pop-large',
      node_count: 10000,
      edge_count: 0,
      nodes: Array.from({ length: 10000 }, (_, i) => ({ id: `agent-${i}`, agent_index: i })),
      edges: [],
    })

    const before = store.populationDisplayNodes
    store.appendMeetingDialogue(1, createArgument({
      participant_index: 0,
      participant_name: 'A0',
      argument: '発話中です。',
    }))

    expect(store.populationDisplayNodes).toBe(before)
    expect(store.populationDisplayNodes).toHaveLength(9998)
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

  it('ネットワーク取得前に届いた人口スタンスを setPopulationNetwork 後も保持する', () => {
    const store = useSocietyGraphStore()

    store.applyPropagationRound([{ i: 7, s: '反対' }])
    store.setPopulationNetwork({
      population_id: 'pop-race',
      node_count: 1,
      edge_count: 0,
      nodes: [{ id: 'pop-7-a', agent_index: 7 }],
      edges: [],
    })

    const popNode = store.graphNodes.find((n) => n.id === 'pop-7-a')
    expect(popNode?.stance).toBe('反対')
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

  it('古い generation で届いた population network は適用しない', () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'sel-0', agent_index: 0, name: 'A0', occupation: '会社員', age: 30, region: '関東' },
    ])
    const capturedGeneration = store.generation

    store.reset()
    const applied = store.setPopulationNetworkIfCurrent({
      population_id: 'stale-pop',
      node_count: 1,
      edge_count: 0,
      nodes: [{ id: 'pop-stale', agent_index: 1 }],
      edges: [],
    }, capturedGeneration)

    expect(applied).toBe(false)
    expect(store.populationNodeCount).toBe(0)
    expect(store.graphNodes).toHaveLength(0)
  })

  it('setPopulationNetwork がエッジ上限を超えると強度上位だけ残す', () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'n-0', agent_index: 0, name: 'A0', occupation: '会社員', age: 30, region: '関東' },
    ])

    // 2 ノード間に上限+1 本のエッジ。1 本だけ極端に弱い強度にする。
    const edges: Array<[number, number, number]> = []
    for (let i = 0; i < POPULATION_EDGE_DISPLAY_CAP; i++) {
      edges.push([0, 1, 0.9])
    }
    edges.push([0, 1, 0.001]) // 最弱: 上限カットで落ちるべき

    store.setPopulationNetwork({
      population_id: 'pop-cap',
      node_count: 2,
      edge_count: edges.length,
      nodes: [
        { id: 'n-0', agent_index: 0 },
        { id: 'n-1', agent_index: 1 },
      ],
      edges,
    })

    const popEdges = store.graphEdges.filter((e) => e.id?.startsWith('pop-edge-'))
    expect(popEdges).toHaveLength(POPULATION_EDGE_DISPLAY_CAP)
    // 最弱エッジ (0.001) は上限カットで除外される
    expect(popEdges.some((e) => e.weight === 0.001)).toBe(false)
  })

  it('updateStancesFromPropagation が liveAgents のスタンスとシフトを更新する', () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'sel-0', agent_index: 0, name: 'A0', occupation: '会社員', age: 30, region: '関東' },
      { id: 'sel-1', agent_index: 1, name: 'A1', occupation: '経営者', age: 40, region: '関西' },
    ])

    store.updateStancesFromPropagation([
      { agentId: 'sel-0', stance: '賛成' },
      { agentId: 'sel-1', stance: '中立' }, // 既定が中立なら変化なし
      { agentId: 'ghost', stance: '反対' }, // liveAgents に居ない: 無視される
    ])

    expect(store.liveAgents.get('sel-0')?.stance).toBe('賛成')
    const shift = store.pendingStanceShifts.find((s) => s.agentId === 'sel-0')
    expect(shift?.toStance).toBe('賛成')
    expect(shift?.reason).toBe('network propagation')
    // 存在しないエージェントはシフトを生まない
    expect(store.pendingStanceShifts.some((s) => s.agentId === 'ghost')).toBe(false)
  })
})
