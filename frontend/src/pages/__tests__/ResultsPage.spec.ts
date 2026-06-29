import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResultsPage from '../ResultsPage.vue'

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  getSimulation: vi.fn(),
  getSimulationReport: vi.fn(),
  getSimulationGraph: vi.fn(),
  getSimulationColonies: vi.fn(),
  submitCodexReview: vi.fn(),
  getCodexHealth: vi.fn(),
  getTranscript: vi.fn(),
  getPropagation: vi.fn(),
  rerunSimulation: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'sim-unsupported' } }),
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

describe('ResultsPage', () => {
  beforeEach(() => {
    push.mockReset()
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
    apiMocks.getSimulationGraph.mockResolvedValue({ nodes: [], edges: [] })
    apiMocks.getSimulationColonies.mockResolvedValue([])
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
})
