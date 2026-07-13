import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SimulationPage from '../SimulationPage.vue'
import { useSimulationStore } from '../../stores/simulationStore'

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  getSimulation: vi.fn(),
  getSimulationColonies: vi.fn(),
  getSimulationGraph: vi.fn(),
  getSimulationTimeline: vi.fn(),
  getSocialGraph: vi.fn(),
  getConversations: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'sim-live-1' } }),
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

vi.mock('../../composables/useSimulationSSE', () => ({
  useSimulationSSE: () => ({
    start: vi.fn(),
    close: vi.fn(),
  }),
}))

describe('SimulationPage', () => {
  beforeEach(() => {
    push.mockReset()
    window.sessionStorage.clear()
    apiMocks.getSimulationGraph.mockResolvedValue({ nodes: [], edges: [] })
    apiMocks.getSimulationTimeline.mockResolvedValue([])
    apiMocks.getSimulationColonies.mockResolvedValue([])
    apiMocks.getSocialGraph.mockResolvedValue({ nodes: [], edges: [], population_id: null })
    apiMocks.getConversations.mockRejectedValue(new Error('not ready'))
  })

  function mountPage() {
    return mount(SimulationPage, {
      global: {
        plugins: [createPinia()],
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          SocietyProgress: { template: '<div>society-progress</div>' },
          SimulationProgress: { template: '<div>simulation-progress</div>' },
          OpinionDistribution: { template: '<div>opinion-distribution</div>' },
          LiveSocietyGraph: { template: '<div>live-society-graph</div>' },
          ColonyGrid: { template: '<div>colony-grid</div>' },
          ActivityFeed: { template: '<div>activity-feed</div>' },
          ForceGraph2D: { template: '<div data-testid="graph-2d">2d-graph</div>' },
        },
      },
    })
  }

  it('uses graph-first live workspace for standard modes', async () => {
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-live-1',
      project_id: null,
      mode: 'single',
      prompt_text: '市場分析',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 0,
      deep_colony_count: 0,
      status: 'running',
      error_message: '',
      pipeline_stage: 'pending',
      stage_progress: {},
      run_id: 'run-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-24T00:00:00Z',
      started_at: '2026-03-24T00:00:10Z',
      completed_at: null,
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="simulation-primary-view"]').text()).toContain('Graph Live')
    expect(wrapper.text()).toContain('Progress')
    expect(wrapper.text()).toContain('Activity')
    expect(wrapper.text()).not.toContain('Society')
  })

  it('uses society-first live workspace for society modes', async () => {
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-live-1',
      project_id: null,
      mode: 'society_first',
      prompt_text: '新規サービス投入',
      template_name: 'scenario_exploration',
      execution_profile: 'standard',
      colony_count: 3,
      deep_colony_count: 0,
      status: 'running',
      error_message: '',
      pipeline_stage: 'pending',
      stage_progress: {},
      run_id: null,
      swarm_id: 'swarm-1',
      metadata: {},
      created_at: '2026-03-24T00:00:00Z',
      started_at: '2026-03-24T00:00:10Z',
      completed_at: null,
    })
    apiMocks.getSimulationColonies.mockResolvedValue([
      {
        id: 'colony-1',
        colony_index: 1,
        perspective_id: 'price',
        perspective_label: 'Price',
        temperature: 0.2,
        adversarial: false,
        status: 'running',
        current_round: 1,
        total_rounds: 3,
        error_message: '',
      },
    ])

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="simulation-primary-view"]').text()).toContain('Society Live')
    // society mode uses consolidated 3-tab layout: Debate / Progress / 分析
    expect(wrapper.text()).toContain('Debate')
    expect(wrapper.text()).toContain('分析')
    expect(wrapper.text()).not.toContain('Colonies')
  })

  it('treats preset standard mode as society live and hydrates existing pulse data', async () => {
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-live-1',
      project_id: null,
      mode: 'standard',
      prompt_text: 'ガソリン車を廃止',
      template_name: 'policy_simulation',
      execution_profile: 'standard',
      colony_count: 0,
      deep_colony_count: 0,
      status: 'running',
      error_message: '',
      pipeline_stage: 'pending',
      stage_progress: {},
      run_id: null,
      swarm_id: null,
      metadata: {
        pulse_result: {
          aggregation: {
            stance_distribution: { 反対: 0.6, 条件付き賛成: 0.4 },
          },
          evaluation: { diversity: 0.8 },
        },
      },
      created_at: '2026-03-24T00:00:00Z',
      started_at: '2026-03-24T00:00:10Z',
      completed_at: null,
    })
    apiMocks.getSocialGraph.mockResolvedValue({
      population_id: 'pop-1',
      nodes: [
        {
          id: 'agent-1',
          agent_index: 1,
          demographics: { occupation: '会社員', age: 45, region: '関東' },
          big_five: {},
          values: {},
          speech_style: '',
          stance: '反対',
          confidence: 0.8,
          reason: '',
          concern: '',
          priority: '',
        },
      ],
      edges: [],
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="simulation-primary-view"]').text()).toContain('Society Live')
    expect(wrapper.text()).toContain('評議会 Round 0')
    expect(apiMocks.getSocialGraph).toHaveBeenCalledWith('sim-live-1')
  })

  it('renders the 2D graph surface for standard modes', async () => {
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-live-1',
      project_id: null,
      mode: 'single',
      prompt_text: '市場分析',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 0,
      deep_colony_count: 0,
      status: 'running',
      error_message: '',
      pipeline_stage: 'pending',
      stage_progress: {},
      run_id: 'run-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-24T00:00:00Z',
      started_at: '2026-03-24T00:00:10Z',
      completed_at: null,
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[data-testid="graph-2d"]').exists()).toBe(true)
    expect(wrapper.find('.graph-canvas-host').exists()).toBe(false)
  })

  it('keeps the execution screen open when loading an already completed simulation', async () => {
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-live-1',
      project_id: null,
      mode: 'single',
      prompt_text: '市場分析',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 0,
      deep_colony_count: 0,
      status: 'completed',
      error_message: '',
      pipeline_stage: 'completed',
      stage_progress: {},
      run_id: 'run-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-24T00:00:00Z',
      started_at: '2026-03-24T00:00:10Z',
      completed_at: '2026-03-24T00:01:10Z',
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(push).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('結果を表示')
  })

  it('redirects to results when a running simulation completes after bootstrap', async () => {
    apiMocks.getSimulation.mockResolvedValue({
      id: 'sim-live-1',
      project_id: null,
      mode: 'single',
      prompt_text: '市場分析',
      template_name: 'business_analysis',
      execution_profile: 'standard',
      colony_count: 0,
      deep_colony_count: 0,
      status: 'running',
      error_message: '',
      pipeline_stage: 'pending',
      stage_progress: {},
      run_id: 'run-1',
      swarm_id: null,
      metadata: {},
      created_at: '2026-03-24T00:00:00Z',
      started_at: '2026-03-24T00:00:10Z',
      completed_at: null,
    })

    mountPage()
    await flushPromises()

    useSimulationStore().setStatus('completed')
    await flushPromises()

    expect(push).toHaveBeenCalledWith('/sim/sim-live-1/results')
  })
})
