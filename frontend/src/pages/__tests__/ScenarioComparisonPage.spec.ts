/**
 * Stream H3: Frontend Integration Test for ScenarioComparisonPage
 *
 * Tests that the page component correctly fetches data, shows loading state,
 * and renders child components (ComparisonBrief, CoalitionMap,
 * OpinionShiftTable, AuditTimeline) when data is available.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ScenarioComparisonPage from '../ScenarioComparisonPage.vue'

// ---------- mocks ----------

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'pair-test-1' } }),
  useRouter: () => ({ push }),
}))

// Mock the SSE composable
const mockStart = vi.fn()
vi.mock('../../composables/useScenarioPairSSE', () => ({
  useScenarioPairSSE: () => ({
    events: { value: [] },
    baselineStatus: { value: 'idle' },
    interventionStatus: { value: 'idle' },
    isComplete: { value: false },
    start: mockStart,
    close: vi.fn(),
  }),
}))

// Mock axios used by scenarioPairStore
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

async function getMockAxios() {
  const mod = await import('axios')
  return (mod as any).__mockInstance
}

const MOCK_PAIR = {
  id: 'pair-test-1',
  population_snapshot_id: 'pop-snap-1',
  baseline_simulation_id: 'sim-baseline-1',
  intervention_simulation_id: 'sim-intervention-1',
  intervention_params: { policy: 'subsidy' },
  decision_context: 'Youth employment subsidy evaluation',
  status: 'completed',
  created_at: '2026-01-15T10:00:00Z',
}

const MOCK_COMPARISON = {
  scenario_pair_id: 'pair-test-1',
  baseline_brief: {
    recommendation: 'Go',
    agreement_score: 0.72,
    decision_summary: 'Baseline analysis summary',
  },
  intervention_brief: {
    recommendation: 'No-Go',
    agreement_score: 0.45,
    decision_summary: 'Intervention analysis summary',
  },
  delta: {
    support_change: -0.27,
    new_concerns: ['Implementation cost too high'],
    coalition_shifts: [],
    key_differences: ['Support among youth dropped by 30%'],
  },
  opinion_shifts_top5: [
    {
      agent_name: 'Tanaka',
      before: 'support',
      after: 'oppose',
      reasoning: 'Cost concerns outweigh benefits',
    },
  ],
  coalition_map: {
    by_age: [
      { group: '18-29', support: 0.4, oppose: 0.6, count: 30 },
      { group: '30-49', support: 0.7, oppose: 0.3, count: 40 },
    ],
    by_region: [
      { group: 'Tokyo', support: 0.6, oppose: 0.4, count: 50 },
    ],
  },
}

function createWrapper() {
  return mount(ScenarioComparisonPage, {
    global: {
      plugins: [createPinia()],
      stubs: {
        ComparisonBrief: { template: '<div data-testid="comparison-brief-stub">ComparisonBrief</div>' },
        CoalitionMap: { template: '<div data-testid="coalition-map-stub">CoalitionMap</div>' },
        OpinionShiftTable: { template: '<div data-testid="opinion-shift-table-stub">OpinionShiftTable</div>' },
        AuditTimeline: { template: '<div data-testid="audit-timeline-stub">AuditTimeline</div>' },
        SimulationProgress: { template: '<div>SimulationProgress</div>' },
      },
    },
  })
}

describe('ScenarioComparisonPage', () => {
  let mockApi: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    mockApi = await getMockAxios()
    vi.clearAllMocks()
  })

  it('shows loading state initially', () => {
    // Do not resolve promises yet so loading persists
    mockApi.get.mockReturnValue(new Promise(() => {}))
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('比較データを読み込んでいます')
  })

  it('fetches scenario pair on mount', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })

    createWrapper()
    await flushPromises()

    // Should have called get for pair and comparison
    expect(mockApi.get).toHaveBeenCalledWith('/scenario-pairs/pair-test-1')
  })

  it('renders page title', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })

    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.text()).toContain('2条件の比較結果')
  })

  it('renders decision context from pair', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })

    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.text()).toContain('Youth employment subsidy evaluation')
  })

  it('renders ComparisonBrief when data arrives', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })

    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.find('[data-testid="comparison-brief-stub"]').exists()).toBe(true)
  })

  it('renders CoalitionMap with mock data', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })

    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.find('[data-testid="coalition-map-stub"]').exists()).toBe(true)
  })

  it('shows error state when fetch fails', async () => {
    mockApi.get.mockRejectedValueOnce(new Error('Network error'))

    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.text()).toContain('Network error')
  })

  it('shows completed status badge for completed pair', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })

    const wrapper = createWrapper()
    await flushPromises()

    const badge = wrapper.find('.status-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe('完了')
  })

  it('shows back button that navigates to home', async () => {
    mockApi.get.mockResolvedValueOnce({ data: MOCK_PAIR })
    mockApi.get.mockResolvedValueOnce({ data: MOCK_COMPARISON })

    const wrapper = createWrapper()
    await flushPromises()

    const backBtn = wrapper.find('.btn-ghost')
    expect(backBtn.exists()).toBe(true)
    await backBtn.trigger('click')
    expect(push).toHaveBeenCalledWith('/')
  })

  it('shows waiting message when pair is not completed and not running', async () => {
    const pendingPair = { ...MOCK_PAIR, status: 'created' }
    mockApi.get.mockResolvedValueOnce({ data: pendingPair })

    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.text()).toContain('2つの分析が終わると、ここに違いが表示されます。')
  })

  it('does not render comparison components when no comparison data', async () => {
    const pendingPair = { ...MOCK_PAIR, status: 'created' }
    mockApi.get.mockResolvedValueOnce({ data: pendingPair })

    const wrapper = createWrapper()
    await flushPromises()

    expect(wrapper.find('[data-testid="comparison-brief-stub"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="coalition-map-stub"]').exists()).toBe(false)
  })
})
