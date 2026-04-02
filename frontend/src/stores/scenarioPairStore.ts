import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
})

export interface ScenarioPair {
  id: string
  population_snapshot_id: string
  baseline_simulation_id: string | null
  intervention_simulation_id: string | null
  intervention_params: Record<string, unknown>
  decision_context: string
  status: string
  created_at: string
}

export interface ComparisonDelta {
  support_change: number
  new_concerns: string[]
  coalition_shifts: Array<Record<string, unknown>>
  key_differences: string[]
}

export interface ComparisonResult {
  scenario_pair_id: string
  baseline_brief: Record<string, unknown>
  intervention_brief: Record<string, unknown>
  delta: ComparisonDelta
  opinion_shifts_top5: Array<Record<string, unknown>>
  coalition_map: Record<string, unknown>
}

export const useScenarioPairStore = defineStore('scenarioPair', () => {
  const currentPair = ref<ScenarioPair | null>(null)
  const comparisonResult = ref<ComparisonResult | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const hasComparison = computed(() => comparisonResult.value !== null)
  const isCompleted = computed(() => currentPair.value?.status === 'completed')
  const isRunning = computed(() =>
    currentPair.value?.status === 'running' || currentPair.value?.status === 'pending',
  )

  async function createScenarioPair(params: {
    population_id: string
    decision_context: string
    intervention_params: Record<string, unknown>
  }) {
    isLoading.value = true
    error.value = null
    try {
      const { data } = await api.post('/scenario-pairs', params)
      currentPair.value = data
      return data as ScenarioPair
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to create scenario pair'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function fetchPair(id: string) {
    isLoading.value = true
    error.value = null
    try {
      const { data } = await api.get(`/scenario-pairs/${id}`)
      currentPair.value = data
      return data as ScenarioPair
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to fetch scenario pair'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function fetchComparison(id: string) {
    isLoading.value = true
    error.value = null
    try {
      const { data } = await api.get(`/scenario-pairs/${id}/comparison`)
      comparisonResult.value = data
      return data as ComparisonResult
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Failed to fetch comparison'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  function reset() {
    currentPair.value = null
    comparisonResult.value = null
    isLoading.value = false
    error.value = null
  }

  return {
    currentPair,
    comparisonResult,
    isLoading,
    error,
    hasComparison,
    isCompleted,
    isRunning,
    createScenarioPair,
    fetchPair,
    fetchComparison,
    reset,
  }
})
