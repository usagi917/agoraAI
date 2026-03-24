import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResultsPage from '../ResultsPage.vue'

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  getSimulation: vi.fn(),
  getSimulationReport: vi.fn(),
  getSimulationGraph: vi.fn(),
  getSimulationGraphHistory: vi.fn(),
  getSimulationColonies: vi.fn(),
  submitSimulationFollowup: vi.fn(),
  rerunSimulation: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'sim-unified-1' } }),
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

vi.mock('../../composables/useForceGraph', () => ({
  useForceGraph: () => ({
    setFullGraph: vi.fn(),
    startGraphTransition: vi.fn(),
    updateGraphTransition: vi.fn(),
    finishGraphTransition: vi.fn(),
    graphError: null,
  }),
}))

const unifiedReport = {
  type: 'unified',
  content: '# 統合レポート\n\n市場参入は推奨されます。',
  sections: {},
  evidence_refs: [],
  run_config: { evidence_mode: 'strict', trust_mode: 'strict' },
  quality: {
    status: 'draft',
    fallback_used: false,
    fallback_reason: '',
    calibration_status: 'uncalibrated',
    trust_level: 'low_trust',
    evidence_available: false,
    evidence_refs_count: 0,
    issues: [],
  },
  verification: null,
  decision_brief: {
    recommendation: 'Go',
    agreement_score: 0.82,
    agreement_breakdown: { society: 0.78, council: 0.85, synthesis: 0.83 },
    decision_summary: '市場参入を進めるが、価格仮説の検証完了を条件にする。',
    why_now: '競争が激化する前に検証順序を固定したい。',
    key_reasons: [
      { reason: '市場成長率が高い', evidence: 'market_view', confidence: 0.84, decision_impact: '需要仮説を補強' },
    ],
    guardrails: [
      { condition: '価格受容性が成立すること', status: '未検証', why_it_matters: '採算が変わる' },
    ],
    recommended_actions: [
      { action: '価格ヒアリングを実施', owner: 'CEO', deadline: '2週間', expected_learning: '価格受容性が分かる', priority: 'high' },
    ],
    options: [
      { label: '即時参入', expected_effect: '先行者優位', risk: '競合の反撃' },
    ],
    strongest_counterargument: '市場が成熟しすぎている',
    risk_factors: [{ condition: '為替変動', impact: '利益率低下' }],
    next_steps: ['市場調査'],
    time_horizon: {
      short_term: { period: '3ヶ月', prediction: '調査完了' },
      mid_term: { period: '1年', prediction: '顧客獲得' },
      long_term: { period: '3年', prediction: '黒字化' },
    },
    stakeholder_reactions: [
      { group: '消費者', reaction: '期待', percentage: 65 },
    ],
  },
  agreement_score: 0.82,
  society_summary: {
    aggregation: {
      average_confidence: 0.75,
      stance_distribution: { 賛成: 0.55, 反対: 0.25, 中立: 0.2 },
      top_concerns: ['価格競争'],
      top_priorities: ['品質'],
    },
    evaluation: { relevance: 0.8 },
  },
  council: {
    participants: [
      { display_name: '田中太郎', role: 'expert', stance: '賛成' },
      { display_name: '佐藤花子', role: 'devil_advocate', stance: '反対' },
    ],
    rounds: [[]],
    synthesis: { consensus_points: ['市場機会は大きい'] },
    devil_advocate_summary: '成熟市場のリスクは軽視されている',
  },
}

describe('ResultsPage — unified report', () => {
  beforeEach(() => {
    push.mockReset()
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-unified-1',
      project_id: null,
      mode: 'unified',
      prompt_text: 'EV市場参入分析',
      template_name: 'market_entry',
      execution_profile: 'standard',
      colony_count: 0,
      deep_colony_count: 0,
      status: 'completed',
      error_message: '',
      pipeline_stage: 'completed',
      stage_progress: {},
      run_id: null,
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-23T00:00:00Z',
      started_at: null,
      completed_at: '2026-03-23T00:02:00Z',
    })
    apiMocks.getSimulationReport.mockResolvedValue(unifiedReport)
    apiMocks.getSimulationGraphHistory.mockResolvedValue([])
    apiMocks.getSimulationGraph.mockResolvedValue({ nodes: [], edges: [] })
    apiMocks.getSimulationColonies.mockResolvedValue([])
  })

  function mountPage() {
    return mount(ResultsPage, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          TemporalSlider: true,
          ProbabilityChart: true,
          ScenarioCompare: true,
          AgreementHeatmap: true,
          AgentMindView: true,
          MemoryStreamViewer: true,
          EvaluationDashboard: true,
          ToMMapVisualization: true,
          SocialNetworkDynamics: true,
          KnowledgeGraphExplorer: true,
        },
      },
    })
  }

  it('shows the decision workspace as the primary view for unified mode', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="results-primary-view"]').text()).toContain('Decision Workspace')
  })

  it('defaults to decision brief tab when a brief is available', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('市場参入を進めるが')
    expect(wrapper.text()).toContain('価格受容性が成立すること')
  })

  it('keeps report text visible below the decision brief workspace', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('統合レポート')
    expect(wrapper.text()).toContain('市場参入は推奨されます')
  })

  it('renders DecisionBrief component when the brief tab is active', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.findComponent({ name: 'DecisionBrief' }).exists()).toBe(true)
  })

  it('shows council participants info for unified mode', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('田中太郎')
    expect(wrapper.text()).toContain('佐藤花子')
  })
})
