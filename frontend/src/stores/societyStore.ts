import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  SocialGraphNode,
  SocialGraphEdge,
  SocialGraphResponse,
  AgentDetailResponse,
  MeetingParticipant,
  MeetingSynthesis,
  ConversationRound,
  NarrativeResponse,
} from '../api/client'
import {
  getSocialGraph,
  getNarrative,
  getAgentDetail,
  getConversations,
} from '../api/client'

export interface SocietyFilters {
  stance: string | null
  region: string | null
  occupation: string | null
  ageRange: [number, number] | null
}

export const useSocietyStore = defineStore('society', () => {
  // === State ===
  const agents = ref<Map<string, SocialGraphNode>>(new Map())
  const socialEdges = ref<SocialGraphEdge[]>([])
  const populationId = ref<string | null>(null)

  const selectedAgentId = ref<string | null>(null)
  const selectedAgentDetail = ref<AgentDetailResponse | null>(null)

  const meetingRounds = ref<ConversationRound[]>([])
  const meetingParticipants = ref<MeetingParticipant[]>([])
  const meetingSynthesis = ref<MeetingSynthesis | null>(null)
  const narrative = ref<NarrativeResponse | null>(null)

  const filters = ref<SocietyFilters>({
    stance: null,
    region: null,
    occupation: null,
    ageRange: null,
  })

  const graphMode = ref<'people' | 'entity'>('people')
  const loading = ref(false)
  const error = ref<string | null>(null)

  // === Computed ===
  const agentList = computed(() => Array.from(agents.value.values()))

  const filteredAgents = computed(() => {
    let list = agentList.value
    const f = filters.value
    if (f.stance) {
      list = list.filter((a) => a.stance === f.stance)
    }
    if (f.region) {
      list = list.filter((a) => a.demographics?.region === f.region)
    }
    if (f.occupation) {
      list = list.filter((a) => a.demographics?.occupation === f.occupation)
    }
    if (f.ageRange) {
      list = list.filter(
        (a) => a.demographics?.age >= f.ageRange![0] && a.demographics?.age <= f.ageRange![1],
      )
    }
    return list
  })

  const agentsByStance = computed(() => {
    const groups: Record<string, SocialGraphNode[]> = {}
    for (const a of agentList.value) {
      const stance = a.stance || '不明'
      if (!groups[stance]) groups[stance] = []
      groups[stance].push(a)
    }
    return groups
  })

  const stanceDistribution = computed(() => {
    const dist: Record<string, number> = {}
    const total = agentList.value.length
    if (total === 0) return dist
    for (const a of agentList.value) {
      const stance = a.stance || '不明'
      dist[stance] = (dist[stance] || 0) + 1
    }
    for (const key of Object.keys(dist)) {
      dist[key] = Math.round((dist[key] / total) * 10000) / 10000
    }
    return dist
  })

  const uniqueRegions = computed(() => {
    const regions = new Set<string>()
    for (const a of agentList.value) {
      if (a.demographics?.region) regions.add(a.demographics.region)
    }
    return Array.from(regions).sort()
  })

  const uniqueOccupations = computed(() => {
    const occupations = new Set<string>()
    for (const a of agentList.value) {
      if (a.demographics?.occupation) occupations.add(a.demographics.occupation)
    }
    return Array.from(occupations).sort()
  })

  const uniqueStances = computed(() => {
    const stances = new Set<string>()
    for (const a of agentList.value) {
      if (a.stance) stances.add(a.stance)
    }
    return Array.from(stances)
  })

  // useForceGraph 用にフォーマット変換
  const graphNodes = computed(() =>
    filteredAgents.value.map((a) => ({
      id: a.id,
      label: `${a.demographics?.occupation || '不明'}, ${a.demographics?.age || '?'}歳`,
      type: 'agent',
      importance_score: a.confidence || 0.5,
      stance: a.stance || '',
      activity_score: 0,
      sentiment_score: 0,
      status: 'active',
      group: a.stance || '不明',
    })),
  )

  const filteredAgentIds = computed(() => new Set(filteredAgents.value.map((a) => a.id)))

  const graphEdges = computed(() =>
    socialEdges.value
      .filter(
        (e) => filteredAgentIds.value.has(e.source) && filteredAgentIds.value.has(e.target),
      )
      .map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        relation_type: e.relation_type,
        weight: e.strength,
        direction: 'undirected',
        status: 'active',
      })),
  )

  // === Actions ===
  async function loadSocialGraph(simId: string) {
    loading.value = true
    error.value = null
    try {
      const data: SocialGraphResponse = await getSocialGraph(simId)
      agents.value = new Map(data.nodes.map((n) => [n.id, n]))
      socialEdges.value = data.edges
      populationId.value = data.population_id
    } catch (e: any) {
      error.value = e.message || 'ソーシャルグラフの読み込みに失敗しました'
    } finally {
      loading.value = false
    }
  }

  async function loadAgentDetail(simId: string, agentId: string) {
    selectedAgentId.value = agentId
    try {
      selectedAgentDetail.value = await getAgentDetail(simId, agentId)
    } catch (e: any) {
      selectedAgentDetail.value = null
    }
  }

  async function loadConversations(simId: string) {
    try {
      const data = await getConversations(simId)
      meetingRounds.value = data.rounds
      meetingParticipants.value = data.participants
      meetingSynthesis.value = data.synthesis
    } catch {
      meetingRounds.value = []
      meetingParticipants.value = []
      meetingSynthesis.value = null
    }
  }

  async function loadNarrative(simId: string) {
    try {
      const data = await getNarrative(simId)
      narrative.value = data.phase_data
    } catch {
      narrative.value = null
    }
  }

  function setFilter(key: keyof SocietyFilters, value: any) {
    filters.value[key] = value
  }

  function clearFilters() {
    filters.value = { stance: null, region: null, occupation: null, ageRange: null }
  }

  function clearSelection() {
    selectedAgentId.value = null
    selectedAgentDetail.value = null
  }

  function $reset() {
    agents.value = new Map()
    socialEdges.value = []
    populationId.value = null
    selectedAgentId.value = null
    selectedAgentDetail.value = null
    meetingRounds.value = []
    meetingParticipants.value = []
    meetingSynthesis.value = null
    narrative.value = null
    filters.value = { stance: null, region: null, occupation: null, ageRange: null }
    graphMode.value = 'people'
    loading.value = false
    error.value = null
  }

  return {
    // State
    agents,
    socialEdges,
    populationId,
    selectedAgentId,
    selectedAgentDetail,
    meetingRounds,
    meetingParticipants,
    meetingSynthesis,
    narrative,
    filters,
    graphMode,
    loading,
    error,
    // Computed
    agentList,
    filteredAgents,
    agentsByStance,
    stanceDistribution,
    uniqueRegions,
    uniqueOccupations,
    uniqueStances,
    graphNodes,
    graphEdges,
    // Actions
    loadSocialGraph,
    loadAgentDetail,
    loadConversations,
    loadNarrative,
    setFilter,
    clearFilters,
    clearSelection,
    $reset,
  }
})
