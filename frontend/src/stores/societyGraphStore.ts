import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { GraphNode, GraphEdge } from './graphStore'
import type { SocialGraphNode, SocialGraphEdge } from '../api/client'
import { useKGEvolutionStore } from './kgEvolutionStore'

type LiveAgentStatus = 'selected' | 'activating' | 'activated' | 'speaking' | 'idle'

interface LiveAgentNode {
  id: string
  agentIndex: number
  label: string
  displayName: string
  occupation: string
  age: number
  region: string
  stance: string | null
  confidence: number
  status: LiveAgentStatus
  speakingText: string | null
  speakingRound: number | null
}

interface LiveEdge {
  id: string
  source: string
  target: string
  relationType: string
  strength: number
}

export interface MeetingArgument {
  participant_name: string
  participant_index: number
  role: string
  expertise?: string
  round?: number
  argument: string
  position?: string
  evidence?: string
  concerns?: string[]
  questions_to_others?: string[]
  addressed_to?: string
  addressed_to_participant_index?: number | null
  belief_update?: string
  round_name?: string
  sub_round?: string
  tension_topic?: string
  is_devil_advocate?: boolean
}

interface ConversationEdge {
  id: string
  source: string
  target: string
  type: 'question' | 'response' | 'general'
  round: number
  intensity: number
}

interface StanceShiftEvent {
  agentId: string
  fromStance: string
  toStance: string
  reason: string
}

/** GET /society/simulations/{id}/population-network のレスポンス */
interface PopulationNetworkPayload {
  population_id: string
  node_count: number
  edge_count: number
  nodes: Array<{ id: string; agent_index: number }>
  /** [source_index, target_index, strength] */
  edges: Array<[number, number, number]>
}

/** SSE population_propagation_round の changes 要素（i=agent_index, s=stance） */
export interface PropagationChange {
  i: number
  s: string
}

/** Canvas 描画コスト保護のための人口エッジ表示上限（強い順に残す） */
export const POPULATION_EDGE_DISPLAY_CAP = 12000

/**
 * Cumulative entry for the SNS-style live feed (SocietyLiveFeed).
 * Unlike `currentArguments`, this buffer is NOT reset on round changes,
 * so it retains the whole meeting history as it streams in.
 */
export interface FeedEntry {
  id: string
  kind: 'dialogue' | 'stance_shift' | 'round'
  round: number
  receivedAt: number
  // dialogue
  participant_name?: string
  role?: string
  position?: string
  argument?: string
  addressed_to?: string
  // stance_shift
  participant?: string
  from?: string
  to?: string
  reason?: string
  // round
  round_name?: string
}

const FEED_MAX = 300

export const useSocietyGraphStore = defineStore('societyGraph', () => {
  const liveAgents = ref<Map<string, LiveAgentNode>>(new Map())
  const liveAgentIdSet = ref<Set<string>>(new Set())
  const liveEdges = ref<LiveEdge[]>([])
  const generation = ref(0)
  const currentRound = ref<number>(0)
  const currentArguments = ref<MeetingArgument[]>([])
  const activationCompleted = ref(0)
  const activationTotal = ref(0)
  const conversationEdges = ref<ConversationEdge[]>([])
  const pendingStanceShifts = ref<StanceShiftEvent[]>([])
  const feedEntries = ref<FeedEntry[]>([])
  // Monotonic counter for feed entry ids that don't have a natural stable key
  // (round markers, stance shifts). Not reset — keys only need per-session uniqueness.
  let feedSeq = 0
  const hoveredEdge = ref<{ id: string; relationType: string; weight: number; sourceId: string; targetId: string } | null>(null)
  const selectedEdge = ref<{ id: string; relationType: string; weight: number; sourceId: string; targetId: string } | null>(null)
  const socialEdgesVisible = ref(true)
  const agentEntityLinksVisible = ref(true)

  // --- 人口レイヤー（全人口伝播の波及描画） ---
  const populationNodes = ref<Array<{ id: string; agentIndex: number }>>([])
  /** エッジは不変なので GraphEdge 変換をキャッシュしておく（30k 件規模） */
  const populationGraphEdges = ref<GraphEdge[]>([])
  const populationStances = ref<Map<number, string>>(new Map())
  const populationVisible = ref(true)

  // === Computed: 2D graph 用の GraphNode/GraphEdge 変換 ===

  const agentList = computed(() => Array.from(liveAgents.value.values()))

  const populationDisplayNodes = computed<GraphNode[]>(() => {
    if (!populationVisible.value || !populationNodes.value.length) return []

    const liveIds = liveAgentIdSet.value
    const stances = populationStances.value
    const nodes: GraphNode[] = []
    for (const p of populationNodes.value) {
      // 選抜済みエージェントは liveAgents 側のリッチなノードを優先
      if (liveIds.has(p.id)) continue
      nodes.push({
        id: p.id,
        label: '',
        type: 'agent',
        importance_score: 0.1,
        stance: stances.get(p.agentIndex) || '',
        activity_score: 0,
        sentiment_score: 0,
        status: 'idle',
        group: 'population',
        tier: 'population',
      })
    }
    return nodes
  })

  const graphNodes = computed<GraphNode[]>(() => {
    const nodes: GraphNode[] = agentList.value.map((a) => ({
      id: a.id,
      label: a.displayName || a.label,
      type: 'agent',
      importance_score: a.confidence || 0.5,
      stance: a.stance || '',
      activity_score: a.status === 'speaking' ? 1 : 0,
      sentiment_score: 0,
      status: a.status,
      group: a.stance || '不明',
    }))

    nodes.push(...populationDisplayNodes.value)

    const kgStore = useKGEvolutionStore()
    if (!kgStore.layerVisible) return nodes

    return [...nodes, ...kgStore.graphNodes]
  })

  const graphEdges = computed<GraphEdge[]>(() => {
    const edges: GraphEdge[] = []

    if (socialEdgesVisible.value) {
      for (const e of liveEdges.value) {
        edges.push({
          id: e.id,
          source: e.source,
          target: e.target,
          relation_type: e.relationType,
          weight: e.strength,
          direction: 'undirected',
          status: 'active',
        })
      }
    }

    if (populationVisible.value && populationGraphEdges.value.length) {
      edges.push(...populationGraphEdges.value)
    }

    const kgStore = useKGEvolutionStore()
    if (kgStore.layerVisible) {
      edges.push(...kgStore.graphEdges)
      if (agentEntityLinksVisible.value) {
        edges.push(...kgStore.agentEntityEdges)
      }
    }

    return edges
  })

  const nodeCount = computed(() => liveAgents.value.size)
  const populationNodeCount = computed(() => populationNodes.value.length)
  const edgeCount = computed(() => graphEdges.value.length)

  const speakingAgents = computed(() =>
    agentList.value.filter((a) => a.status === 'speaking'),
  )

  // --- Phase 1a: インタラクション頻度マトリクス ---

  /** ペアワイズのインタラクション回数 (key: "agentId-A::agentId-B" ソート済み) */
  const interactionMatrix = computed(() => {
    const matrix = new Map<string, number>()
    const agentsByIndex = new Map<number, string>()
    for (const agent of liveAgents.value.values()) {
      agentsByIndex.set(agent.agentIndex, agent.id)
    }

    for (const arg of currentArguments.value) {
      const sourceId = agentsByIndex.get(arg.participant_index)
      if (!sourceId) continue
      const targetId = arg.addressed_to_participant_index != null
        ? agentsByIndex.get(arg.addressed_to_participant_index)
        : undefined
      if (targetId && targetId !== sourceId) {
        const key = [sourceId, targetId].sort().join('::')
        matrix.set(key, (matrix.get(key) || 0) + 1)
      }
    }
    return matrix
  })

  /** 2エージェント間の会話を取得 */
  function getConversationBetween(agentIdA: string, agentIdB: string): MeetingArgument[] {
    const agentA = liveAgents.value.get(agentIdA)
    const agentB = liveAgents.value.get(agentIdB)
    if (!agentA || !agentB) return []

    const indexA = agentA.agentIndex
    const indexB = agentB.agentIndex

    return currentArguments.value.filter((arg) =>
      (arg.participant_index === indexA && arg.addressed_to_participant_index === indexB)
      || (arg.participant_index === indexB && arg.addressed_to_participant_index === indexA)
      || (arg.participant_index === indexA && arg.addressed_to?.includes(agentB.displayName || agentB.label))
      || (arg.participant_index === indexB && arg.addressed_to?.includes(agentA.displayName || agentA.label)),
    )
  }

  /** ペアのインタラクション数を取得 */
  function getInteractionCount(agentIdA: string, agentIdB: string): number {
    const key = [agentIdA, agentIdB].sort().join('::')
    return interactionMatrix.value.get(key) || 0
  }

  // === Actions ===

  function getMeetingArgumentKey(round: number, arg: MeetingArgument) {
    return [
      round,
      arg.participant_index,
      arg.participant_name,
      arg.sub_round || '',
      arg.addressed_to || '',
      arg.argument,
    ].join('::')
  }

  function _pushFeedEntry(entry: FeedEntry) {
    feedEntries.value.push(entry)
    if (feedEntries.value.length > FEED_MAX) {
      feedEntries.value.splice(0, feedEntries.value.length - FEED_MAX)
    }
  }

  /** Insert a round marker unless the most recent marker already covers this round. */
  function _recordRoundMarker(round: number, roundName?: string) {
    for (let i = feedEntries.value.length - 1; i >= 0; i--) {
      if (feedEntries.value[i].kind === 'round') {
        if (feedEntries.value[i].round === round) return
        break
      }
    }
    _pushFeedEntry({
      id: `round-${round}-${feedSeq++}`,
      kind: 'round',
      round,
      receivedAt: Date.now(),
      round_name: roundName,
    })
  }

  function _recordDialogueEntry(round: number, arg: MeetingArgument) {
    const id = getMeetingArgumentKey(round, arg)
    if (feedEntries.value.some((e) => e.kind === 'dialogue' && e.id === id)) return
    _pushFeedEntry({
      id,
      kind: 'dialogue',
      round,
      receivedAt: Date.now(),
      participant_name: arg.participant_name,
      role: arg.role,
      position: arg.position,
      argument: arg.argument,
      addressed_to: arg.addressed_to,
    })
  }

  /**
   * Record a whole batch of arguments into the feed (round marker + each dialogue).
   * Used by the bulk paths (setMeetingRound / completeMeetingRound) so that
   * arguments delivered only via meeting_round_completed (SSE reconnect / gap fill)
   * still reach the feed. Existing dedup keys prevent double-recording.
   */
  function _recordFeedArguments(round: number, args: MeetingArgument[]) {
    _recordRoundMarker(round, args.find((a) => a.round_name)?.round_name)
    for (const arg of args) {
      _recordDialogueEntry(round, arg)
    }
  }

  function getRestingStatus(agent: LiveAgentNode): LiveAgentStatus {
    if (agent.stance || agent.status === 'activated' || agent.status === 'idle') {
      return 'activated'
    }
    return 'selected'
  }

  function clearActiveSpeakers() {
    let changed = false
    for (const agent of liveAgents.value.values()) {
      if (agent.status === 'speaking') {
        agent.status = getRestingStatus(agent)
        agent.speakingText = null
        agent.speakingRound = null
        changed = true
      }
    }
    if (changed) {
      liveAgents.value = new Map(liveAgents.value)
    }
  }

  function setActiveSpeaker(arg: MeetingArgument, round: number) {
    clearActiveSpeakers()

    for (const agent of liveAgents.value.values()) {
      if (agent.agentIndex === arg.participant_index) {
        agent.status = 'speaking'
        agent.speakingText = arg.argument
        agent.speakingRound = round
        liveAgents.value = new Map(liveAgents.value)
        break
      }
    }
  }

  function mergeMeetingArguments(round: number, args: MeetingArgument[]) {
    const seen = new Set(currentArguments.value.map((arg) => getMeetingArgumentKey(round, arg)))

    for (const arg of args) {
      const key = getMeetingArgumentKey(round, arg)
      if (!seen.has(key)) {
        currentArguments.value.push(arg)
        seen.add(key)
      }
    }
  }

  function setSelectedAgents(agents: Array<{
    id?: string
    agent_index: number
    name: string
    display_name?: string
    occupation: string
    age: number
    region: string
  }>) {
    const map = new Map<string, LiveAgentNode>()
    for (const a of agents) {
      const id = a.id || `agent-${a.agent_index}`
      const displayName = a.display_name || ''
      const fallbackLabel = `${a.occupation || '不明'}, ${a.age || '?'}歳`
      map.set(id, {
        id,
        agentIndex: a.agent_index,
        label: fallbackLabel,
        displayName,
        occupation: a.occupation,
        age: a.age,
        region: a.region,
        stance: null,
        confidence: 0.5,
        status: 'selected',
        speakingText: null,
        speakingRound: null,
      })
    }
    liveAgents.value = map
    liveAgentIdSet.value = new Set(map.keys())
  }

  function updateActivationProgress(completed: number, total: number) {
    activationCompleted.value = completed
    activationTotal.value = total
    // 活性化中のエージェントのステータスを順次更新
    const agents = Array.from(liveAgents.value.values())
    for (let i = 0; i < agents.length; i++) {
      if (i < completed) {
        if (agents[i].status === 'selected' || agents[i].status === 'activating') {
          agents[i].status = 'activated'
        }
      } else if (i === completed) {
        agents[i].status = 'activating'
      }
    }
    // trigger reactivity
    liveAgents.value = new Map(liveAgents.value)
  }

  function hydrateWithSocialGraph(nodes: SocialGraphNode[], edges: SocialGraphEdge[]) {
    // 既存のliveAgentsを実データで更新
    for (const node of nodes) {
      const id = node.id
      const existing = liveAgents.value.get(id)
      if (existing) {
        existing.stance = node.stance || null
        existing.confidence = node.confidence || 0.5
        existing.label = `${node.demographics?.occupation || '不明'}, ${node.demographics?.age || '?'}歳`
        existing.occupation = node.demographics?.occupation || ''
        existing.age = node.demographics?.age || 0
        existing.region = node.demographics?.region || ''
        existing.status = 'activated'
      } else {
        // SSEで拾えなかったエージェント（フォールバック）
        liveAgents.value.set(id, {
          id,
          agentIndex: node.agent_index,
          label: `${node.demographics?.occupation || '不明'}, ${node.demographics?.age || '?'}歳`,
          displayName: '',
          occupation: node.demographics?.occupation || '',
          age: node.demographics?.age || 0,
          region: node.demographics?.region || '',
          stance: node.stance || null,
          confidence: node.confidence || 0.5,
          status: 'activated',
          speakingText: null,
          speakingRound: null,
        })
      }
    }
    // trigger reactivity
    liveAgents.value = new Map(liveAgents.value)
    liveAgentIdSet.value = new Set(liveAgents.value.keys())

    // エッジを設定
    liveEdges.value = edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      relationType: e.relation_type,
      strength: e.strength,
    }))
  }

  /**
   * ソーシャルグラフの「構造」だけを早期に投入する（選抜直後の SSE
   * `society_social_graph_structure` 用）。stance/status は活性化の出力なので
   * ここでは一切触らず、意見未確定の暫定暖色の窓を維持したまま本物の関係性の輪を描く。
   * stance を含む完全版は後続の hydrateWithSocialGraph が上書きする。
   */
  function setSocialEdges(edges: SocialGraphEdge[]) {
    liveEdges.value = edges.map((e) => ({
      id: e.id || `edge-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      relationType: e.relation_type,
      strength: e.strength,
    }))
  }

  function setMeetingRound(round: number, args: MeetingArgument[]) {
    currentRound.value = round
    currentArguments.value = []
    conversationEdges.value = []
    mergeMeetingArguments(round, args)
    _recordFeedArguments(round, args)
    clearActiveSpeakers()

    // 会話エッジを生成
    _buildConversationEdges(round, currentArguments.value)
  }

  function appendMeetingDialogue(round: number, arg: MeetingArgument) {
    if (currentRound.value !== round) {
      currentRound.value = round
      currentArguments.value = []
      conversationEdges.value = []
      _recordRoundMarker(round, arg.round_name)
    }

    mergeMeetingArguments(round, [arg])
    _recordDialogueEntry(round, arg)
    setActiveSpeaker(arg, round)
    _buildConversationEdges(round, currentArguments.value)
  }

  function completeMeetingRound(round: number, args: MeetingArgument[] = []) {
    if (currentRound.value !== round) {
      currentRound.value = round
      currentArguments.value = []
      conversationEdges.value = []
    }

    if (args.length > 0) {
      mergeMeetingArguments(round, args)
      _recordFeedArguments(round, args)
    }

    clearActiveSpeakers()
    _buildConversationEdges(round, currentArguments.value)
  }

  function _buildConversationEdges(round: number, args: MeetingArgument[]) {
    const newEdges: ConversationEdge[] = []
    const agentsByName = new Map<string, string>()
    const agentsByIndex = new Map<number, string>()

    // 名前/インデックス → agentId マッピング構築
    for (const agent of liveAgents.value.values()) {
      agentsByIndex.set(agent.agentIndex, agent.id)
      if (agent.displayName) agentsByName.set(agent.displayName, agent.id)
      agentsByName.set(agent.label, agent.id)
    }

    const speakerIds = args.map((a) => agentsByIndex.get(a.participant_index)).filter(Boolean) as string[]

    for (const arg of args) {
      const sourceId = agentsByIndex.get(arg.participant_index)
      if (!sourceId) continue

      // 明示的な応答先がある場合はそれを優先
      const explicitTargetId = arg.addressed_to_participant_index != null
        ? agentsByIndex.get(arg.addressed_to_participant_index)
        : undefined
      if (explicitTargetId && explicitTargetId !== sourceId) {
        const edgeId = `conv-${round}-${sourceId}-${explicitTargetId}-${arg.sub_round || 'reply'}`
        if (!newEdges.find((e) => e.id === edgeId)) {
          newEdges.push({
            id: edgeId,
            source: sourceId,
            target: explicitTargetId,
            type: 'response',
            round,
            intensity: arg.sub_round === 'direct_exchange' ? 1 : 0.9,
          })
        }
      }

      // questions_to_others → question エッジ
      if (arg.questions_to_others?.length) {
        for (const q of arg.questions_to_others) {
          // 質問文中にエージェント名が含まれるか探す
          for (const [name, id] of agentsByName) {
            if (id !== sourceId && q.includes(name)) {
              newEdges.push({
                id: `conv-${round}-${sourceId}-${id}-q`,
                source: sourceId,
                target: id,
                type: 'question',
                round,
                intensity: 0.9,
              })
            }
          }
        }
      }

      // Round 2以降: 他のスピーカー全員への暗黙的 response エッジ
      if (round > 1 && !explicitTargetId) {
        for (const targetId of speakerIds) {
          if (targetId !== sourceId) {
            const edgeId = `conv-${round}-${sourceId}-${targetId}-r`
            if (!newEdges.find((e) => e.id === edgeId)) {
              newEdges.push({
                id: edgeId,
                source: sourceId,
                target: targetId,
                type: 'response',
                round,
                intensity: 0.6,
              })
            }
          }
        }
      }

      // Round 1: 全スピーカー間に general エッジ
      if (round === 1) {
        for (const targetId of speakerIds) {
          if (targetId !== sourceId) {
            const id1 = [sourceId, targetId].sort().join('-')
            const edgeId = `conv-${round}-${id1}-g`
            if (!newEdges.find((e) => e.id === edgeId)) {
              newEdges.push({
                id: edgeId,
                source: sourceId,
                target: targetId,
                type: 'general',
                round,
                intensity: 0.4,
              })
            }
          }
        }
      }
    }

    conversationEdges.value = newEdges
  }

  function clearSpeaking() {
    clearActiveSpeakers()
    currentArguments.value = []
    conversationEdges.value = []
  }

  function addStanceShifts(shifts: Array<{ participant: string; from: string; to: string; reason: string }>) {
    // Feed records every reported shift, independent of whether it maps to a live agent node.
    // Dedup by content key (participant/from/to/round) so a re-sent meeting_completed
    // does not double-record; the feedSeq-based id stays unique for the :key.
    const round = currentRound.value
    for (const shift of shifts) {
      const isDuplicate = feedEntries.value.some((e) =>
        e.kind === 'stance_shift'
        && e.round === round
        && e.participant === shift.participant
        && e.from === shift.from
        && e.to === shift.to,
      )
      if (isDuplicate) continue
      _pushFeedEntry({
        id: `stance-${shift.participant}-${shift.from}-${shift.to}-${feedSeq++}`,
        kind: 'stance_shift',
        round,
        receivedAt: Date.now(),
        participant: shift.participant,
        from: shift.from,
        to: shift.to,
        reason: shift.reason,
      })
    }

    const events: StanceShiftEvent[] = []
    for (const shift of shifts) {
      // 参加者名からagentIdを検索
      for (const agent of liveAgents.value.values()) {
        const nameMatch = agent.displayName === shift.participant
          || agent.label.includes(shift.participant)
          || shift.participant.includes(agent.occupation)
        if (nameMatch) {
          events.push({
            agentId: agent.id,
            fromStance: shift.from,
            toStance: shift.to,
            reason: shift.reason,
          })
          // スタンスも実際に更新
          agent.stance = shift.to
          break
        }
      }
    }
    if (events.length) {
      pendingStanceShifts.value = events
      liveAgents.value = new Map(liveAgents.value)
    }
  }

  function clearStanceShifts() {
    pendingStanceShifts.value = []
  }

  /**
   * Bulk update agent stances from propagation results.
   * Maps opinion values to stance labels and triggers visual updates.
   */
  function updateStancesFromPropagation(stanceUpdates: Array<{ agentId: string; stance: string }>) {
    const shifts: typeof pendingStanceShifts.value = []
    for (const update of stanceUpdates) {
      const agent = liveAgents.value.get(update.agentId)
      if (agent && agent.stance !== update.stance) {
        shifts.push({
          agentId: update.agentId,
          fromStance: agent.stance || '中立',
          toStance: update.stance,
          reason: 'network propagation',
        })
        agent.stance = update.stance
      }
    }
    if (shifts.length > 0) {
      pendingStanceShifts.value = shifts
      liveAgents.value = new Map(liveAgents.value)
    }
  }

  function setPopulationNetwork(payload: PopulationNetworkPayload) {
    const idByIndex = new Map<number, string>()
    const nodeIndices = new Set<number>()
    populationNodes.value = payload.nodes.map((n) => {
      idByIndex.set(n.agent_index, n.id)
      nodeIndices.add(n.agent_index)
      return { id: n.id, agentIndex: n.agent_index }
    })

    let rawEdges = payload.edges
    if (rawEdges.length > POPULATION_EDGE_DISPLAY_CAP) {
      rawEdges = [...rawEdges]
        .sort((a, b) => b[2] - a[2])
        .slice(0, POPULATION_EDGE_DISPLAY_CAP)
    }

    const edges: GraphEdge[] = []
    rawEdges.forEach(([si, ti, strength], i) => {
      const source = idByIndex.get(si)
      const target = idByIndex.get(ti)
      if (!source || !target) return
      edges.push({
        id: `pop-edge-${i}`,
        source,
        target,
        relation_type: 'acquaintance',
        weight: strength,
        direction: 'undirected',
        status: 'active',
      })
    })
    populationGraphEdges.value = edges

    const preservedStances = new Map<number, string>()
    for (const [agentIndex, stance] of populationStances.value) {
      if (nodeIndices.has(agentIndex)) {
        preservedStances.set(agentIndex, stance)
      }
    }
    populationStances.value = preservedStances
  }

  function setPopulationNetworkIfCurrent(payload: PopulationNetworkPayload, expectedGeneration: number): boolean {
    if (generation.value !== expectedGeneration) return false
    setPopulationNetwork(payload)
    return true
  }

  /** 伝播ラウンドのスタンス変化を反映する（人口レイヤー + 選抜エージェント両対応） */
  function applyPropagationRound(changes: PropagationChange[]) {
    if (!changes.length) return

    const liveByIndex = new Map<number, LiveAgentNode>()
    for (const agent of liveAgents.value.values()) {
      liveByIndex.set(agent.agentIndex, agent)
    }

    const nextStances = new Map(populationStances.value)
    let liveChanged = false
    for (const change of changes) {
      const live = liveByIndex.get(change.i)
      if (live) {
        if (live.stance !== change.s) {
          live.stance = change.s
          liveChanged = true
        }
      } else {
        nextStances.set(change.i, change.s)
      }
    }

    populationStances.value = nextStances
    if (liveChanged) {
      liveAgents.value = new Map(liveAgents.value)
    }
  }

  function setHoveredEdge(edge: typeof hoveredEdge.value) {
    hoveredEdge.value = edge
  }

  function setSelectedEdge(edge: typeof selectedEdge.value) {
    selectedEdge.value = edge
  }

  function reset() {
    generation.value += 1
    liveAgents.value = new Map()
    liveAgentIdSet.value = new Set()
    liveEdges.value = []
    currentRound.value = 0
    currentArguments.value = []
    activationCompleted.value = 0
    activationTotal.value = 0
    conversationEdges.value = []
    pendingStanceShifts.value = []
    feedEntries.value = []
    hoveredEdge.value = null
    selectedEdge.value = null
    socialEdgesVisible.value = true
    agentEntityLinksVisible.value = true
    populationNodes.value = []
    populationGraphEdges.value = []
    populationStances.value = new Map()
    populationVisible.value = true
  }

  return {
    // State
    liveAgents,
    liveEdges,
    currentRound,
    currentArguments,
    activationCompleted,
    activationTotal,
    conversationEdges,
    pendingStanceShifts,
    feedEntries,
    hoveredEdge,
    selectedEdge,
    socialEdgesVisible,
    agentEntityLinksVisible,
    generation,
    populationNodes,
    populationGraphEdges,
    populationStances,
    populationVisible,
    // Computed
    agentList,
    populationDisplayNodes,
    graphNodes,
    graphEdges,
    nodeCount,
    edgeCount,
    populationNodeCount,
    speakingAgents,
    interactionMatrix,
    // Actions
    setSelectedAgents,
    getConversationBetween,
    getInteractionCount,
    updateActivationProgress,
    setSocialEdges,
    hydrateWithSocialGraph,
    setMeetingRound,
    appendMeetingDialogue,
    completeMeetingRound,
    clearSpeaking,
    addStanceShifts,
    clearStanceShifts,
    updateStancesFromPropagation,
    setPopulationNetwork,
    setPopulationNetworkIfCurrent,
    applyPropagationRound,
    setHoveredEdge,
    setSelectedEdge,
    reset,
  }
})
