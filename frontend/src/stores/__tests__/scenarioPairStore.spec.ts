import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  useScenarioPairStore,
  type ScenarioPair,
  type ComparisonResult,
} from '../scenarioPairStore'

// Mock axios
vi.mock('axios', () => {
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
  }
  return {
    default: {
      create: () => mockAxiosInstance,
    },
    __mockInstance: mockAxiosInstance,
  }
})

// Get the mock instance
async function getMockAxios() {
  const mod = await import('axios')
  return (mod as any).__mockInstance
}

const MOCK_PAIR: ScenarioPair = {
  id: 'pair-1',
  population_snapshot_id: 'pop-1',
  baseline_simulation_id: 'sim-baseline',
  intervention_simulation_id: 'sim-intervention',
  intervention_params: { policy: 'new-tax' },
  decision_context: 'Should we implement the new tax policy?',
  status: 'completed',
  created_at: '2026-01-01T00:00:00Z',
}

const MOCK_COMPARISON: ComparisonResult = {
  scenario_pair_id: 'pair-1',
  baseline_brief: { recommendation: 'Go', agreement_score: 0.72 },
  intervention_brief: { recommendation: 'No-Go', agreement_score: 0.45 },
  delta: {
    support_change: -0.27,
    new_concerns: ['Tax burden on small businesses'],
    coalition_shifts: [{ group: 'youth', from: 'support', to: 'oppose' }],
    key_differences: ['Support dropped significantly among urban voters'],
  },
  opinion_shifts_top5: [
    { agent_name: 'Agent A', before: 'support', after: 'oppose', reasoning: 'Changed due to cost concerns' },
  ],
  coalition_map: {
    by_age: {
      '18-30': { support: 0.3, oppose: 0.7 },
      '31-50': { support: 0.6, oppose: 0.4 },
    },
  },
}

describe('scenarioPairStore', () => {
  let mockApi: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    mockApi = await getMockAxios()
    vi.clearAllMocks()
  })

  it('has correct initial state', () => {
    const store = useScenarioPairStore()
    expect(store.currentPair).toBeNull()
    expect(store.comparisonResult).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
    expect(store.hasComparison).toBe(false)
  })

  it('fetchPair sets currentPair', async () => {
    mockApi.get.mockResolvedValue({ data: MOCK_PAIR })
    const store = useScenarioPairStore()

    const result = await store.fetchPair('pair-1')

    expect(result).toEqual(MOCK_PAIR)
    expect(store.currentPair).toEqual(MOCK_PAIR)
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('fetchPair sets error on failure', async () => {
    mockApi.get.mockRejectedValue({ message: 'Network error' })
    const store = useScenarioPairStore()

    await expect(store.fetchPair('pair-1')).rejects.toBeTruthy()

    expect(store.error).toBe('Network error')
    expect(store.isLoading).toBe(false)
  })

  it('fetchComparison sets comparisonResult', async () => {
    mockApi.get.mockResolvedValue({ data: MOCK_COMPARISON })
    const store = useScenarioPairStore()

    const result = await store.fetchComparison('pair-1')

    expect(result).toEqual(MOCK_COMPARISON)
    expect(store.comparisonResult).toEqual(MOCK_COMPARISON)
    expect(store.hasComparison).toBe(true)
  })

  it('createScenarioPair posts and sets currentPair', async () => {
    mockApi.post.mockResolvedValue({ data: MOCK_PAIR })
    const store = useScenarioPairStore()

    const result = await store.createScenarioPair({
      population_id: 'pop-1',
      decision_context: 'test context',
      intervention_params: { policy: 'new-tax' },
    })

    expect(result).toEqual(MOCK_PAIR)
    expect(store.currentPair).toEqual(MOCK_PAIR)
  })

  it('isCompleted computed returns true when status is completed', async () => {
    mockApi.get.mockResolvedValue({ data: MOCK_PAIR })
    const store = useScenarioPairStore()

    await store.fetchPair('pair-1')

    expect(store.isCompleted).toBe(true)
  })

  it('isRunning computed returns true when status is running', async () => {
    const runningPair = { ...MOCK_PAIR, status: 'running' }
    mockApi.get.mockResolvedValue({ data: runningPair })
    const store = useScenarioPairStore()

    await store.fetchPair('pair-1')

    expect(store.isRunning).toBe(true)
  })

  it('reset clears all state', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })
    const store = useScenarioPairStore()

    await store.fetchPair('pair-1')
    await store.fetchComparison('pair-1')
    expect(store.currentPair).toBeTruthy()
    expect(store.comparisonResult).toBeTruthy()

    store.reset()

    expect(store.currentPair).toBeNull()
    expect(store.comparisonResult).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
  })
})
