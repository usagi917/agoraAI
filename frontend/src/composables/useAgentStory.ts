import { ref, watch, computed, type Ref } from 'vue'
import { getAgentDetail, type AgentDetailResponse } from '../api/client'
import { useSocietyGraphStore } from '../stores/societyGraphStore'

export interface OpinionJourneyItem {
  type: 'contribution' | 'stance_shift'
  round: number
  content: string
  addressedTo?: string
  fromStance?: string
  toStance?: string
  roundName?: string
}

export interface InfluenceEntry {
  agentName: string
  count: number
}

export function useAgentStory(simId: string, agentId: Ref<string | null>) {
  const societyGraphStore = useSocietyGraphStore()

  const agentDetail = ref<AgentDetailResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  let lastFetchedId: string | null = null
  let abortController: AbortController | null = null

  async function fetchDetail(id: string) {
    abortController?.abort()
    abortController = new AbortController()
    loading.value = true
    error.value = null
    try {
      agentDetail.value = await getAgentDetail(simId, id, { signal: abortController.signal })
      lastFetchedId = id
    } catch (e: any) {
      if (e?.name === 'CanceledError' || e?.name === 'AbortError') return
      error.value = e?.message ?? 'データの取得に失敗しました'
    } finally {
      loading.value = false
    }
  }

  watch(
    agentId,
    (newId) => {
      if (!newId) {
        agentDetail.value = null
        error.value = null
        lastFetchedId = null
        return
      }
      fetchDetail(newId)
    },
    { immediate: true },
  )

  // Re-fetch on round change during live simulation
  watch(
    () => societyGraphStore.currentRound,
    () => {
      if (agentId.value && agentId.value === lastFetchedId) {
        fetchDetail(agentId.value)
      }
    },
  )

  const opinionJourney = computed<OpinionJourneyItem[]>(() => {
    if (!agentDetail.value) return []

    const items: OpinionJourneyItem[] = []

    for (const c of agentDetail.value.meeting_contributions) {
      items.push({
        type: 'contribution',
        round: c.round,
        content: c.argument,
        addressedTo: c.addressed_to || undefined,
        roundName: c.round_name || undefined,
      })

      // If there's a belief update, include it as a stance shift marker
      if (c.belief_update) {
        items.push({
          type: 'stance_shift',
          round: c.round,
          content: c.belief_update,
        })
      }
    }

    items.sort((a, b) => a.round - b.round)
    return items
  })

  const influenceMap = computed<InfluenceEntry[]>(() => {
    if (!agentDetail.value) return []

    const counts = new Map<string, number>()
    for (const c of agentDetail.value.meeting_contributions) {
      if (c.addressed_to) {
        counts.set(c.addressed_to, (counts.get(c.addressed_to) ?? 0) + 1)
      }
    }

    return Array.from(counts.entries())
      .map(([agentName, count]) => ({ agentName, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
  })

  return { agentDetail, opinionJourney, influenceMap, loading, error }
}
