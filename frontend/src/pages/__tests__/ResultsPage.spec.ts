import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { h, onUnmounted } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResultsPage from '../ResultsPage.vue'
import { useGraphStore } from '../../stores/graphStore'
import { useSocietyGraphStore } from '../../stores/societyGraphStore'

// 実際の LiveSocietyGraph は onUnmounted で societyGraphStore.reset() を呼ぶ。
// パネル開閉の再 hydrate 回帰テストでは、その reset 挙動を再現するスタブを使う
// （素の <div> スタブでは reset が起きず回帰を検出できない）。
const societyResetStub = {
  setup() {
    const store = useSocietyGraphStore()
    onUnmounted(() => store.reset())
    return () => h('div', { 'data-testid': 'stub-society-graph' })
  },
}

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  getSimulation: vi.fn(),
  getSimulationReport: vi.fn(),
  getSimulationGraph: vi.fn(),
  getSimulationColonies: vi.fn(),
  getSocialGraph: vi.fn(),
  getPopulationNetwork: vi.fn(),
  submitCodexReview: vi.fn(),
  getCodexHealth: vi.fn(),
  getTranscript: vi.fn(),
  getPropagation: vi.fn(),
  rerunSimulation: vi.fn(),
}))

// 重い canvas コンポーネントは結果ページのグラフパネル検証では軽量スタブで代替する。
const graphStubs = {
  ForceGraph2D: {
    props: ['nodes', 'edges'],
    template: '<div data-testid="stub-force-graph">{{ nodes.length }}n/{{ edges.length }}e</div>',
  },
  LiveSocietyGraph: {
    props: ['simulationId', 'spotlightAgentId'],
    template: '<div data-testid="stub-society-graph" />',
  },
}

// グラフパネル系テストで共通利用する mount スタブ一式と society シミュレーション。
const graphPanelStubs = {
  RouterLink: { template: '<a><slot /></a>' },
  ProbabilityChart: true,
  ScenarioCompare: true,
  AgreementHeatmap: true,
  PropagationDashboard: true,
  ...graphStubs,
}

const societySimResponse = {
  id: 'sim-society',
  project_id: null,
  mode: 'society',
  prompt_text: '社会反応',
  template_name: 'society',
  execution_profile: 'standard',
  colony_count: 1,
  deep_colony_count: 0,
  status: 'completed',
  error_message: '',
  pipeline_stage: 'completed',
  stage_progress: {},
  run_id: 'run-soc',
  swarm_id: null,
  metadata: {},
  created_at: '2026-03-21T00:00:00Z',
  started_at: null,
  completed_at: '2026-03-21T00:01:00Z',
}

// グラフパネル系テストの mount 設定を一元化する。ストア検証が必要なテストは
// 返却された pinia 経由で検証し、事前投入が必要なテストは pinia を渡す。
function mountResults(pinia = createPinia()) {
  const wrapper = mount(ResultsPage, {
    global: { plugins: [pinia], stubs: graphPanelStubs },
  })
  return { wrapper, pinia }
}

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'sim-unsupported' } }),
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

describe('ResultsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    push.mockReset()
    window.sessionStorage.clear()
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-unsupported',
      project_id: null,
      mode: 'single',
      prompt_text: 'prompt only',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 1,
      deep_colony_count: 0,
      status: 'completed',
      error_message: '',
      pipeline_stage: 'completed',
      stage_progress: {},
      run_id: 'run-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-21T00:00:00Z',
      started_at: null,
      completed_at: '2026-03-21T00:01:00Z',
    })
    apiMocks.getSimulationReport.mockResolvedValue({
      type: 'single',
      id: 'report-1',
      run_id: 'run-1',
      content: 'short report',
      sections: {},
      status: 'completed',
      evidence_refs: [],
      run_config: { evidence_mode: 'strict', trust_mode: 'strict' },
      verification: {
        status: 'failed',
        score: 0.4,
        issues: ['unsupported_quality'],
        warnings: [],
        metrics: {},
      },
      quality: {
        status: 'unsupported',
        fallback_used: false,
        fallback_reason: '',
        calibration_status: 'uncalibrated',
        evidence_mode: 'strict',
        trust_level: 'low_trust',
        evidence_available: true,
        evidence_refs_count: 1,
        document_refs_count: 0,
        prompt_refs_count: 1,
        unsupported_reason: 'strict_document_evidence_required',
        issues: ['strict_document_evidence_required'],
      },
    })
    apiMocks.getSimulationGraph.mockResolvedValue({ nodes: [], edges: [], round: 0 })
    apiMocks.getSimulationColonies.mockResolvedValue([])
    apiMocks.getSocialGraph.mockResolvedValue({ population_id: 'pop-1', nodes: [], edges: [] })
    apiMocks.getPopulationNetwork.mockResolvedValue({
      population_id: 'pop-1',
      node_count: 0,
      edge_count: 0,
      nodes: [],
      edges: [],
    })
    apiMocks.getCodexHealth.mockResolvedValue({
      enabled: false,
      available: false,
      initialized: false,
      transport: 'stdio',
      error: '',
    })
    apiMocks.getTranscript.mockResolvedValue([])
    apiMocks.getPropagation.mockResolvedValue(null)
  })

  it('renders unsupported quality state with strict error context', async () => {
    const wrapper = mount(ResultsPage, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          TemporalSlider: true,
          ProbabilityChart: true,
          ScenarioCompare: true,
          AgreementHeatmap: true,
          PropagationDashboard: true,
        },
      },
    })

    await flushPromises()

    const banner = wrapper.get('[data-testid="quality-banner"]')
    expect(banner.text()).toContain('Unsupported')
    expect(banner.text()).toContain('strict_document_evidence_required')
    expect(banner.text()).toContain('verification=failed')
  })

  it('disables AI check action when unavailable', async () => {
    const wrapper = mount(ResultsPage, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          TemporalSlider: true,
          ProbabilityChart: true,
          ScenarioCompare: true,
          SocietyTimeline: true,
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

    await flushPromises()

    expect(wrapper.text()).toContain('レビュー機能の準備ができていません')
    expect(wrapper.get('.ai-check-primary').attributes('disabled')).toBeDefined()
  })

  it('renders society_first backtest and observed intervention comparison', async () => {
    apiMocks.getSimulation.mockResolvedValueOnce({
      id: 'sim-society-first',
      project_id: null,
      mode: 'society_first',
      prompt_text: '新規サービス投入',
      template_name: 'scenario_exploration',
      execution_profile: 'standard',
      colony_count: 3,
      deep_colony_count: 0,
      status: 'completed',
      error_message: '',
      pipeline_stage: 'completed',
      stage_progress: {},
      run_id: null,
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-21T00:00:00Z',
      started_at: null,
      completed_at: '2026-03-21T00:01:00Z',
    })
    apiMocks.getSimulationReport.mockResolvedValueOnce({
      type: 'society_first',
      content: '# report',
      sections: {},
      society_summary: {
        aggregation: {
          average_confidence: 0.71,
          stance_distribution: { 賛成: 0.45 },
        },
        selected_count: 100,
      },
      issue_candidates: [],
      selected_issues: [],
      issue_colonies: [],
      intervention_comparison: [
        {
          intervention_id: 'price_reduction',
          label: '価格変更',
          change_summary: '初期費用を引き下げる',
          affected_issues: ['価格受容性'],
          comparison_mode: 'observed',
          expected_effect: 'uplift +9.0pt / downside +0.0pt',
          observed_uplift: 0.09,
          observed_downside: 0,
          uncertainty: 0.22,
          supporting_evidence: [
            {
              case_id: 'case-1',
              title: '2025 関西ローンチ',
              metric: 'adoption_rate',
              metric_label: '採用率',
              baseline: 0.18,
              outcome: 0.27,
              signed_delta: 0.09,
              summary: '2025 関西ローンチ: 採用率 +9.0pt',
              evidence: ['初月の採用率が改善した'],
            },
          ],
        },
      ],
      backtest: {
        schema_version: 1,
        input_format: {
          schema_version: 1,
          historical_cases: [
            {
              case_id: 'case-001',
              title: '2025 関西ローンチ',
              observed_at: '2025-10-01',
              baseline_metrics: {
                adoption_rate: 0.18,
                conversion_rate: 0.09,
              },
              outcome: {
                issue_label: '価格受容性',
                summary: '価格改定後も本格導入は遅れたが試験導入は増えた',
                actual_scenario: '価格障壁で導入が遅れる',
                metrics: {
                  adoption_rate: 0.27,
                  conversion_rate: 0.13,
                },
                tags: ['価格', '導入'],
              },
              interventions: [
                {
                  intervention_id: 'price_reduction',
                  label: '価格変更',
                  baseline_metrics: { adoption_rate: 0.18 },
                  outcome_metrics: { adoption_rate: 0.27 },
                  evidence: ['初月の採用率が改善した'],
                },
              ],
            },
            {
              case_id: 'case-002',
              title: '2025 自治体 PoC 規制調整',
              observed_at: '2025-11-15',
              baseline_metrics: {
                approval_rate: 0.36,
                regulatory_risk: 0.68,
              },
              outcome: {
                issue_label: '規制対応',
                summary: '事前調整で承認率が改善した',
                actual_scenario: '制度整合で採用が回復する',
                metrics: {
                  approval_rate: 0.52,
                  regulatory_risk: 0.49,
                },
                tags: ['規制', '承認'],
              },
              interventions: [
                {
                  intervention_id: 'regulatory_alignment',
                  label: '規制対応',
                  baseline_metrics: { approval_rate: 0.36, regulatory_risk: 0.68 },
                  outcome_metrics: { approval_rate: 0.52, regulatory_risk: 0.49 },
                  evidence: ['自治体レビュー通過率が改善した'],
                },
              ],
            },
          ],
        },
        matching_rules: {},
        historical_cases: [
          {
            case_id: 'case-001',
            title: '2025 関西ローンチ',
            observed_at: '2025-10-01',
            baseline_metrics: { adoption_rate: 0.18, conversion_rate: 0.09 },
            outcome: {
              issue_label: '価格受容性',
              summary: '価格改定後も本格導入は遅れたが試験導入は増えた',
              actual_scenario: '価格障壁で導入が遅れる',
              metrics: { adoption_rate: 0.27, conversion_rate: 0.13 },
              tags: ['価格', '導入'],
            },
            interventions: [],
          },
          {
            case_id: 'case-002',
            title: '2025 自治体 PoC 規制調整',
            observed_at: '2025-11-15',
            baseline_metrics: { approval_rate: 0.36, regulatory_risk: 0.68 },
            outcome: {
              issue_label: '規制対応',
              summary: '事前調整で承認率が改善した',
              actual_scenario: '制度整合で採用が回復する',
              metrics: { approval_rate: 0.52, regulatory_risk: 0.49 },
              tags: ['規制', '承認'],
            },
            interventions: [],
          },
        ],
        status: 'ready',
        summary: {
          case_count: 2,
          compared_case_count: 2,
          hit_count: 1,
          partial_hit_count: 1,
          miss_count: 0,
          hit_rate: 0.5,
          partial_hit_rate: 0.5,
          issue_hit_count: 2,
          issue_hit_rate: 1,
          scenario_probability_brier: 0.08,
          mean_reciprocal_rank: 0.75,
        },
        cases: [
          {
            case_id: 'case-1',
            title: '2025 関西ローンチ',
            observed_at: '2025-10-01',
            baseline_metrics: {},
            outcome: {
              issue_label: '価格受容性',
              summary: '価格改定後も本格導入は遅れた',
              actual_scenario: '価格障壁で導入が遅れる',
              metrics: {},
              tags: [],
            },
            interventions: [],
            best_match: {
              issue_id: 'issue-1',
              issue_label: '価格受容性',
              scenario_description: '価格障壁で導入が遅れる',
              predicted_score: 0.73,
              actual_summary: '価格改定後も本格導入は遅れた',
              actual_scenario: '価格障壁で導入が遅れる',
              match_score: 0.89,
              label_match: 1,
              text_overlap: 0.8,
              tag_overlap: 0,
              verdict: 'hit',
              reasons: ['issue_label_match'],
            },
            scenario_matches: [],
            issue_results: [],
            summary: { hit_count: 1, partial_hit_count: 0, miss_count: 0 },
          },
          {
            case_id: 'case-2',
            title: '2025 自治体 PoC 規制調整',
            observed_at: '2025-11-15',
            baseline_metrics: {},
            outcome: {
              issue_label: '規制対応',
              summary: '事前調整で承認率が改善した',
              actual_scenario: '制度整合で採用が回復する',
              metrics: {},
              tags: [],
            },
            interventions: [],
            best_match: {
              issue_id: 'issue-2',
              issue_label: '規制対応',
              scenario_description: '制度整合で採用が回復する',
              predicted_score: 0.63,
              actual_summary: '事前調整で承認率が改善した',
              actual_scenario: '制度整合で採用が回復する',
              match_score: 0.61,
              label_match: 1,
              text_overlap: 0.42,
              tag_overlap: 0,
              verdict: 'partial_hit',
              reasons: ['issue_label_match', 'scenario_text_overlap'],
            },
            scenario_matches: [],
            issue_results: [],
            summary: { hit_count: 0, partial_hit_count: 1, miss_count: 0 },
          },
        ],
      },
      scenarios: [],
      evidence_refs: [],
      run_config: { evidence_mode: 'strict', trust_mode: 'strict' },
      quality: {
        status: 'draft',
        fallback_used: false,
        fallback_reason: '',
        calibration_status: 'uncalibrated',
        evidence_mode: 'strict',
        trust_level: 'low_trust',
        evidence_available: false,
        evidence_refs_count: 0,
        document_refs_count: 0,
        prompt_refs_count: 0,
        issues: [],
      },
      verification: {
        status: 'passed',
        score: 1,
        issues: [],
        warnings: [],
        metrics: {},
      },
    })

    const wrapper = mount(ResultsPage, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          TemporalSlider: true,
          ProbabilityChart: true,
          ScenarioCompare: true,
          AgreementHeatmap: true,
          PropagationDashboard: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('実測比較')
    expect(wrapper.text()).toContain('Backtest')
    expect(wrapper.text()).toContain('2025 関西ローンチ')
    expect(wrapper.text()).toContain('2025 自治体 PoC 規制調整')
    expect(wrapper.text()).toContain('Hit')
    expect(wrapper.text()).toContain('Partial')
  })

  it('renders the knowledge graph panel from backend graph state (graph mode)', async () => {
    apiMocks.getSimulationGraph.mockResolvedValueOnce({
      round: 2,
      nodes: [
        { id: 'n1', label: '論点A', type: 'issue', importance_score: 0.8, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
        { id: 'n2', label: '論点B', type: 'issue', importance_score: 0.6, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2', relation_type: 'related', weight: 0.5, direction: 'undirected', status: 'active' },
      ],
    })

    const { wrapper } = mountResults()

    await flushPromises()

    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    const stub = panel.get('[data-testid="stub-force-graph"]')
    expect(stub.text()).toBe('2n/1e')
    expect(wrapper.find('[data-testid="stub-society-graph"]').exists()).toBe(false)
  })

  it('hydrates and renders the social graph panel (society mode)', async () => {
    apiMocks.getSimulation.mockResolvedValueOnce({
      id: 'sim-society',
      project_id: null,
      mode: 'society',
      prompt_text: '社会反応',
      template_name: 'society',
      execution_profile: 'standard',
      colony_count: 1,
      deep_colony_count: 0,
      status: 'completed',
      error_message: '',
      pipeline_stage: 'completed',
      stage_progress: {},
      run_id: 'run-soc',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-21T00:00:00Z',
      started_at: null,
      completed_at: '2026-03-21T00:01:00Z',
    })
    apiMocks.getSocialGraph.mockResolvedValueOnce({
      population_id: 'pop-1',
      nodes: [
        { id: 'agent-0', agent_index: 0, demographics: { occupation: '教師', age: 40, region: '関西' }, big_five: {}, values: {}, speech_style: '', stance: '賛成', confidence: 0.7, reason: '', concern: '', priority: '' },
        { id: 'agent-1', agent_index: 1, demographics: { occupation: '会社員', age: 33, region: '関東' }, big_five: {}, values: {}, speech_style: '', stance: '反対', confidence: 0.6, reason: '', concern: '', priority: '' },
      ],
      edges: [
        { id: 'se1', source: 'agent-0', target: 'agent-1', relation_type: 'friend', strength: 0.8 },
      ],
    })
    apiMocks.getPopulationNetwork.mockResolvedValueOnce({
      population_id: 'pop-1',
      node_count: 2,
      edge_count: 1,
      nodes: [{ id: 'agent-0', agent_index: 0 }, { id: 'agent-1', agent_index: 1 }],
      edges: [[0, 1, 0.5]],
    })

    const { wrapper } = mountResults()

    await flushPromises()

    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    expect(panel.find('[data-testid="stub-society-graph"]').exists()).toBe(true)
    expect(panel.find('[data-testid="stub-force-graph"]').exists()).toBe(false)
    expect(apiMocks.getSocialGraph).toHaveBeenCalled()
    expect(apiMocks.getPopulationNetwork).toHaveBeenCalled()
  })

  it('collapsing the panel unmounts the heavy graph child (v-if)', async () => {
    apiMocks.getSimulationGraph.mockResolvedValueOnce({
      round: 1,
      nodes: [
        { id: 'n1', label: 'A', type: 'issue', importance_score: 0.5, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
      ],
      edges: [],
    })

    const { wrapper } = mountResults()

    await flushPromises()

    // 初期は開いていて、重いグラフ子（ForceGraph2D）がマウントされている。
    expect(wrapper.find('[data-testid="results-graph-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stub-force-graph"]').exists()).toBe(true)

    await wrapper.get('[data-testid="results-graph-toggle"]').trigger('click')

    // 折りたたむと body ごと v-if で unmount され、重い子はメインスレッドから外れる。
    expect(wrapper.find('[data-testid="results-graph-body"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="stub-force-graph"]').exists()).toBe(false)

    await wrapper.get('[data-testid="results-graph-toggle"]').trigger('click')

    // 再度開くと再マウントされる（レイアウト再実行は許容）。
    expect(wrapper.find('[data-testid="results-graph-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stub-force-graph"]').exists()).toBe(true)
  })

  it('re-hydrates the social graph when the panel is reopened (society mode)', async () => {
    // society モードでは、閉じると LiveSocietyGraph の onUnmounted が
    // societyGraphStore.reset() を呼ぶ。開き直したときに再 hydrate されず
    // 空状態のまま固定されないことを保証する回帰テスト。
    apiMocks.getSimulation.mockResolvedValue(societySimResponse)
    apiMocks.getSocialGraph.mockResolvedValue({
      population_id: 'pop-1',
      nodes: [
        { id: 'agent-0', agent_index: 0, demographics: { occupation: '教師', age: 40, region: '関西' }, big_five: {}, values: {}, speech_style: '', stance: '賛成', confidence: 0.7, reason: '', concern: '', priority: '' },
        { id: 'agent-1', agent_index: 1, demographics: { occupation: '会社員', age: 33, region: '関東' }, big_five: {}, values: {}, speech_style: '', stance: '反対', confidence: 0.6, reason: '', concern: '', priority: '' },
      ],
      edges: [
        { id: 'se1', source: 'agent-0', target: 'agent-1', relation_type: 'friend', strength: 0.8 },
      ],
    })
    apiMocks.getPopulationNetwork.mockResolvedValue({
      population_id: 'pop-1',
      node_count: 2,
      edge_count: 1,
      nodes: [{ id: 'agent-0', agent_index: 0 }, { id: 'agent-1', agent_index: 1 }],
      edges: [[0, 1, 0.5]],
    })

    const wrapper = mount(ResultsPage, {
      global: {
        plugins: [createPinia()],
        // reset を再現するスタブに差し替えて実挙動を再現する。
        stubs: { ...graphPanelStubs, LiveSocietyGraph: societyResetStub },
      },
    })

    await flushPromises()

    // 初期 hydrate で社会グラフが描画される。
    expect(wrapper.find('[data-testid="stub-society-graph"]').exists()).toBe(true)
    expect(apiMocks.getSocialGraph).toHaveBeenCalledTimes(1)

    // 閉じる → 子 unmount → onUnmounted が societyGraphStore.reset() を呼ぶ。
    await wrapper.get('[data-testid="results-graph-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="results-graph-body"]').exists()).toBe(false)

    // 再度開く → データが失われているので再 hydrate され、空状態にならない。
    await wrapper.get('[data-testid="results-graph-toggle"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="results-graph-empty"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="stub-society-graph"]').exists()).toBe(true)
    expect(apiMocks.getSocialGraph).toHaveBeenCalledTimes(2)
  })

  it('shows an empty state when there is no graph data', async () => {
    const { wrapper } = mountResults()

    await flushPromises()

    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    expect(panel.find('[data-testid="results-graph-empty"]').exists()).toBe(true)
    expect(panel.find('[data-testid="stub-force-graph"]').exists()).toBe(false)
    expect(panel.find('[data-testid="stub-society-graph"]').exists()).toBe(false)
  })

  it('does not repopulate graphStore after unmount (stale knowledge-graph response)', async () => {
    // hydrateGraph の getSimulationGraph を保留にして、解決前に unmount する。
    let resolveGraph: (value: unknown) => void = () => {}
    apiMocks.getSimulationGraph.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveGraph = resolve
      }),
    )

    const { wrapper, pinia } = mountResults()

    await flushPromises()
    wrapper.unmount()

    // unmount 後に遅れて解決したレスポンスはストアへ書き戻されないこと。
    resolveGraph({
      round: 3,
      nodes: [
        { id: 'late', label: '遅延', type: 'issue', importance_score: 1, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
      ],
      edges: [],
    })
    await flushPromises()

    setActivePinia(pinia)
    expect(useGraphStore().nodes.length).toBe(0)
  })

  it('does not repopulate societyGraphStore after unmount (stale social-graph response)', async () => {
    apiMocks.getSimulation.mockResolvedValueOnce({
      id: 'sim-society',
      project_id: null,
      mode: 'society',
      prompt_text: '社会反応',
      template_name: 'society',
      execution_profile: 'standard',
      colony_count: 1,
      deep_colony_count: 0,
      status: 'completed',
      error_message: '',
      pipeline_stage: 'completed',
      stage_progress: {},
      run_id: 'run-soc',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-21T00:00:00Z',
      started_at: null,
      completed_at: '2026-03-21T00:01:00Z',
    })
    let resolveSocial: (value: unknown) => void = () => {}
    apiMocks.getSocialGraph.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSocial = resolve
      }),
    )

    const { wrapper, pinia } = mountResults()

    await flushPromises()
    wrapper.unmount()

    resolveSocial({
      population_id: 'pop-1',
      nodes: [
        { id: 'agent-0', agent_index: 0, demographics: { occupation: '教師', age: 40, region: '関西' }, big_five: {}, values: {}, speech_style: '', stance: '賛成', confidence: 0.7, reason: '', concern: '', priority: '' },
        { id: 'agent-1', agent_index: 1, demographics: { occupation: '会社員', age: 33, region: '関東' }, big_five: {}, values: {}, speech_style: '', stance: '反対', confidence: 0.6, reason: '', concern: '', priority: '' },
      ],
      edges: [
        { id: 'se1', source: 'agent-0', target: 'agent-1', relation_type: 'friend', strength: 0.8 },
      ],
    })
    await flushPromises()

    setActivePinia(pinia)
    expect(useSocietyGraphStore().nodeCount).toBe(0)
  })

  it('clears stale graphStore and shows empty state when the graph fetch fails', async () => {
    apiMocks.getSimulationGraph.mockRejectedValueOnce(new Error('graph unavailable'))

    const pinia = createPinia()
    // 直前のシミュレーションが残したナレッジグラフを事前投入しておく。
    setActivePinia(pinia)
    useGraphStore().setFullState(
      [
        { id: 'stale', label: '古い論点', type: 'issue', importance_score: 1, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
      ],
      [],
    )

    const { wrapper } = mountResults(pinia)

    await flushPromises()

    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    expect(panel.find('[data-testid="results-graph-empty"]').exists()).toBe(true)
    expect(panel.find('[data-testid="stub-force-graph"]').exists()).toBe(false)
    expect(useGraphStore().nodes.length).toBe(0)
  })

  it('keeps fetching the population network and shows empty state when social-graph fails (society mode)', async () => {
    apiMocks.getSimulation.mockResolvedValueOnce(societySimResponse)
    apiMocks.getSocialGraph.mockRejectedValueOnce(new Error('social graph unavailable'))
    apiMocks.getPopulationNetwork.mockResolvedValueOnce({
      population_id: 'pop-1',
      node_count: 2,
      edge_count: 1,
      nodes: [{ id: 'agent-0', agent_index: 0 }, { id: 'agent-1', agent_index: 1 }],
      edges: [[0, 1, 0.5]],
    })

    const { wrapper } = mountResults()

    await flushPromises()

    // 社会グラフ（liveAgents）の取得に失敗しても空状態を表示。
    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    expect(panel.find('[data-testid="results-graph-empty"]').exists()).toBe(true)
    expect(panel.find('[data-testid="stub-society-graph"]').exists()).toBe(false)
    // 並列取得なので人口ネットワークの取得は引き続き実行される。
    expect(apiMocks.getSocialGraph).toHaveBeenCalled()
    expect(apiMocks.getPopulationNetwork).toHaveBeenCalled()
  })

  it('restores collapsed panel state from sessionStorage and persists toggles', async () => {
    window.sessionStorage.setItem('results-graph-open:sim-unsupported', 'closed')

    const { wrapper } = mountResults()

    await flushPromises()

    // 復元: 折りたたみ状態なので body（と重い子）は存在しない。
    expect(wrapper.find('[data-testid="results-graph-body"]').exists()).toBe(false)

    await wrapper.get('[data-testid="results-graph-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="results-graph-body"]').exists()).toBe(true)
    expect(window.sessionStorage.getItem('results-graph-open:sim-unsupported')).toBe('open')

    await wrapper.get('[data-testid="results-graph-toggle"]').trigger('click')
    expect(window.sessionStorage.getItem('results-graph-open:sim-unsupported')).toBe('closed')
  })

  it('does not start hydrateGraph when unmounted during onMounted awaits', async () => {
    // getSimulation を保留にして、解決前に unmount する。
    let resolveSim: (value: unknown) => void = () => {}
    apiMocks.getSimulation.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSim = resolve
      }),
    )
    // hydrateGraph が誤って走れば graphStore に反映されるノードを仕込んでおく。
    apiMocks.getSimulationGraph.mockResolvedValue({
      round: 9,
      nodes: [
        { id: 'should-not-load', label: 'X', type: 'issue', importance_score: 1, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
      ],
      edges: [],
    })

    const { wrapper, pinia } = mountResults()

    await flushPromises()
    wrapper.unmount()

    resolveSim({
      id: 'sim-unsupported',
      project_id: null,
      mode: 'single',
      prompt_text: 'prompt only',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 1,
      deep_colony_count: 0,
      status: 'completed',
      error_message: '',
      pipeline_stage: 'completed',
      stage_progress: {},
      run_id: 'run-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-21T00:00:00Z',
      started_at: null,
      completed_at: '2026-03-21T00:01:00Z',
    })
    await flushPromises()

    // isUnmounted ガードにより hydrateGraph は開始されず、グラフ取得も走らない。
    expect(apiMocks.getSimulationGraph).not.toHaveBeenCalled()
    setActivePinia(pinia)
    expect(useGraphStore().nodes.length).toBe(0)
  })

  it('handles a null graph response without throwing (defensive empty state)', async () => {
    apiMocks.getSimulationGraph.mockResolvedValueOnce(null)

    const { wrapper, pinia } = mountResults()

    await flushPromises()

    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    expect(panel.find('[data-testid="results-graph-empty"]').exists()).toBe(true)
    expect(panel.find('[data-testid="stub-force-graph"]').exists()).toBe(false)
    setActivePinia(pinia)
    expect(useGraphStore().nodes.length).toBe(0)
  })

  it('binds knowledge-graph title and metric labels', async () => {
    apiMocks.getSimulationGraph.mockResolvedValueOnce({
      round: 2,
      nodes: [
        { id: 'n1', label: '論点A', type: 'issue', importance_score: 0.8, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
        { id: 'n2', label: '論点B', type: 'issue', importance_score: 0.6, stance: '', activity_score: 0, sentiment_score: 0, status: 'active', group: 'g1' },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2', relation_type: 'related', weight: 0.5, direction: 'undirected', status: 'active' },
      ],
    })

    const { wrapper } = mountResults()

    await flushPromises()

    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    expect(panel.text()).toContain('Knowledge Graph')
    const metrics = panel.get('.results-graph-metrics')
    expect(metrics.text()).toContain('2')
    expect(metrics.text()).toContain('nodes')
    expect(metrics.text()).toContain('1')
    expect(metrics.text()).toContain('edges')
  })

  it('binds social-graph title and agent metric label (society mode)', async () => {
    apiMocks.getSimulation.mockResolvedValueOnce(societySimResponse)
    apiMocks.getSocialGraph.mockResolvedValueOnce({
      population_id: 'pop-1',
      nodes: [
        { id: 'agent-0', agent_index: 0, demographics: { occupation: '教師', age: 40, region: '関西' }, big_five: {}, values: {}, speech_style: '', stance: '賛成', confidence: 0.7, reason: '', concern: '', priority: '' },
        { id: 'agent-1', agent_index: 1, demographics: { occupation: '会社員', age: 33, region: '関東' }, big_five: {}, values: {}, speech_style: '', stance: '反対', confidence: 0.6, reason: '', concern: '', priority: '' },
      ],
      edges: [
        { id: 'se1', source: 'agent-0', target: 'agent-1', relation_type: 'friend', strength: 0.8 },
      ],
    })
    apiMocks.getPopulationNetwork.mockResolvedValueOnce({
      population_id: 'pop-1',
      node_count: 2,
      edge_count: 1,
      nodes: [{ id: 'agent-0', agent_index: 0 }, { id: 'agent-1', agent_index: 1 }],
      edges: [[0, 1, 0.5]],
    })

    const { wrapper } = mountResults()

    await flushPromises()

    const panel = wrapper.get('[data-testid="results-graph-panel"]')
    expect(panel.text()).toContain('Social Graph')
    const metrics = panel.get('.results-graph-metrics')
    expect(metrics.text()).toContain('agents')
    expect(metrics.text()).toContain('2')
  })
})
