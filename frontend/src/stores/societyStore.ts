import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  SocialGraphNode,
  SocialGraphEdge,
  SocialGraphResponse,
  MeetingParticipant,
  MeetingSynthesis,
  ConversationRound,
} from '../api/client'
import {
  getSocialGraph,
  getConversations,
} from '../api/client'

export const useSocietyStore = defineStore('society', () => {
  const agents = ref<Map<string, SocialGraphNode>>(new Map())
  const socialEdges = ref<SocialGraphEdge[]>([])
  const populationId = ref<string | null>(null)

  const meetingRounds = ref<ConversationRound[]>([])
  const meetingParticipants = ref<MeetingParticipant[]>([])
  const meetingSynthesis = ref<MeetingSynthesis | null>(null)

  const loading = ref(false)
  const error = ref<string | null>(null)

  const agentList = computed(() => Array.from(agents.value.values()))

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

  function $reset() {
    agents.value = new Map()
    socialEdges.value = []
    populationId.value = null
    meetingRounds.value = []
    meetingParticipants.value = []
    meetingSynthesis.value = null
    loading.value = false
    error.value = null
  }

  return {
    agents,
    socialEdges,
    populationId,
    meetingRounds,
    meetingParticipants,
    meetingSynthesis,
    loading,
    error,
    agentList,
    loadSocialGraph,
    loadConversations,
    $reset,
  }
})
