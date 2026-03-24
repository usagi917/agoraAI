import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { GraphNode, GraphEdge } from './graphStore'
import type { SocialGraphNode, SocialGraphEdge } from '../api/client'
import { useKGEvolutionStore } from './kgEvolutionStore'

export type LiveAgentStatus = 'selected' | 'activating' | 'activated' | 'speaking' | 'idle'

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
  argument: string
  position?: string
  questions_to_others?: string[]
}

export interface ConversationEdge {
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

const STANCE_COLORS: Record<string, string> = {
  '賛成': '#22c55e',
  '条件付き賛成': '#86efac',
  '中立': '#a3a3a3',
  '条件付き反対': '#fca5a5',
  '反対': '#ef4444',
}

export { STANCE_COLORS }

export const useSocietyGraphStore = defineStore('societyGraph', () => {
  const liveAgents = ref<Map<string, LiveAgentNode>>(new Map())
  const liveEdges = ref<LiveEdge[]>([])
  const currentRound = ref<number>(0)
  const currentArguments = ref<MeetingArgument[]>([])
  const activationCompleted = ref(0)
  const activationTotal = ref(0)
  const conversationEdges = ref<ConversationEdge[]>([])
  const pendingStanceShifts = ref<StanceShiftEvent[]>([])
  const hoveredEdge = ref<{ id: string; relationType: string; weight: number; sourceId: string; targetId: string } | null>(null)
  const selectedEdge = ref<{ id: string; relationType: string; weight: number; sourceId: string; targetId: string } | null>(null)

  // === Computed: useForceGraph 用の GraphNode/GraphEdge 変換 ===

  const agentList = computed(() => Array.from(liveAgents.value.values()))

  const graphNodes = computed<GraphNode[]>(() => {
    const agentNodes = agentList.value.map((a) => ({
      id: a.id,
      label: a.displayName || a.label,
      type: 'agent',
      importance_score: a.displayName ? 0.85 : (a.confidence || 0.5),
      stance: a.stance || '',
      activity_score: a.status === 'speaking' ? 1 : 0,
      sentiment_score: 0,
      status: a.status,
      group: a.stance || '不明',
    }))

    const kgStore = useKGEvolutionStore()
    if (!kgStore.layerVisible) return agentNodes

    return [...agentNodes, ...kgStore.graphNodes]
  })

  const graphEdges = computed<GraphEdge[]>(() => {
    const socialEdges = liveEdges.value
      .filter((e) => e.strength > 0.3)
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        relation_type: e.relationType,
        weight: e.strength,
        direction: 'undirected',
        status: 'active',
      }))

    const kgStore = useKGEvolutionStore()
    if (!kgStore.layerVisible) return socialEdges

    return [...socialEdges, ...kgStore.graphEdges, ...kgStore.agentEntityEdges]
  })

  const nodeCount = computed(() => liveAgents.value.size)
  const edgeCount = computed(() => graphEdges.value.length)

  const speakingAgents = computed(() =>
    agentList.value.filter((a) => a.status === 'speaking'),
  )

  // === Actions ===

  function setSelectedAgents(agents: Array<{
    agent_index: number
    name: string
    display_name?: string
    occupation: string
    age: number
    region: string
  }>) {
    const map = new Map<string, LiveAgentNode>()
    for (const a of agents) {
      const id = `agent-${a.agent_index}`
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

    // エッジを設定
    liveEdges.value = edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      relationType: e.relation_type,
      strength: e.strength,
    }))
  }

  function setMeetingRound(round: number, args: MeetingArgument[]) {
    currentRound.value = round
    currentArguments.value = args

    // 前回のspeaking状態をクリア
    for (const agent of liveAgents.value.values()) {
      if (agent.status === 'speaking') {
        agent.status = 'idle'
        agent.speakingText = null
        agent.speakingRound = null
      }
    }

    // 発言者をspeaking状態にする
    for (const arg of args) {
      for (const agent of liveAgents.value.values()) {
        if (agent.agentIndex === arg.participant_index) {
          agent.status = 'speaking'
          agent.speakingText = arg.argument
          agent.speakingRound = round
          break
        }
      }
    }
    // trigger reactivity
    liveAgents.value = new Map(liveAgents.value)

    // 会話エッジを生成
    _buildConversationEdges(round, args)
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
      if (round > 1) {
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
    for (const agent of liveAgents.value.values()) {
      if (agent.status === 'speaking') {
        agent.status = 'idle'
        agent.speakingText = null
        agent.speakingRound = null
      }
    }
    liveAgents.value = new Map(liveAgents.value)
    currentArguments.value = []
    conversationEdges.value = []
  }

  function addStanceShifts(shifts: Array<{ participant: string; from: string; to: string; reason: string }>) {
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

  function setHoveredEdge(edge: typeof hoveredEdge.value) {
    hoveredEdge.value = edge
  }

  function setSelectedEdge(edge: typeof selectedEdge.value) {
    selectedEdge.value = edge
  }

  function reset() {
    liveAgents.value = new Map()
    liveEdges.value = []
    currentRound.value = 0
    currentArguments.value = []
    activationCompleted.value = 0
    activationTotal.value = 0
    conversationEdges.value = []
    pendingStanceShifts.value = []
    hoveredEdge.value = null
    selectedEdge.value = null
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
    hoveredEdge,
    selectedEdge,
    // Computed
    agentList,
    graphNodes,
    graphEdges,
    nodeCount,
    edgeCount,
    speakingAgents,
    // Actions
    setSelectedAgents,
    updateActivationProgress,
    hydrateWithSocialGraph,
    setMeetingRound,
    clearSpeaking,
    addStanceShifts,
    clearStanceShifts,
    setHoveredEdge,
    setSelectedEdge,
    reset,
  }
})
