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
  useRoute: () => ({ params: { id: 'sim-unsupported' } }),
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

vi.mock('../../composables/useForceGraph', () => ({
  useForceGraph: () => ({
    setFullGraph: vi.fn(),
  }),
}))

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
    apiMocks.getSimulationGraphHistory.mockResolvedValue([])
    apiMocks.getSimulationGraph.mockResolvedValue({ nodes: [], edges: [] })
    apiMocks.getSimulationColonies.mockResolvedValue([])
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

    const banner = wrapper.get('[data-testid="quality-banner"]')
    expect(banner.text()).toContain('Unsupported')
    expect(banner.text()).toContain('strict_document_evidence_required')
    expect(banner.text()).toContain('verification=failed')
  })
})
