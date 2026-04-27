import { ref, watch, computed, type Ref } from 'vue'
import { getAgentDetail, type AgentDetailResponse } from '../api/client'
import { useSocietyGraphStore } from '../stores/societyGraphStore'

interface OpinionJourneyItem {
  type: 'contribution' | 'stance_shift'
  round: number
  content: string
  addressedTo?: string
  roundName?: string
}

interface InfluenceEntry {
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
    const controller = new AbortController()
    abortController = controller
    loading.value = true
    error.value = null
    try {
      const detail = await getAgentDetail(simId, id, { signal: controller.signal })
      if (controller.signal.aborted || abortController !== controller || agentId.value !== id) {
        return
      }
      agentDetail.value = detail
      lastFetchedId = id
    } catch (e: any) {
      if (e?.name === 'CanceledError' || e?.name === 'AbortError') return
      error.value = e?.message ?? `エージェント ${id} の詳細データの取得に失敗しました`
    } finally {
      if (abortController === controller) {
        abortController = null
        loading.value = false
      }
    }
  }

  watch(
    agentId,
    (newId) => {
      if (!newId) {
        abortController?.abort()
        abortController = null
        agentDetail.value = null
        loading.value = false
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
