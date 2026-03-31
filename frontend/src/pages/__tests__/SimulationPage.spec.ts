import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import SimulationPage from '../SimulationPage.vue'

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  getSimulation: vi.fn(),
  getSimulationColonies: vi.fn(),
  getSimulationGraph: vi.fn(),
  getSimulationTimeline: vi.fn(),
}))

const pulseMocks = vi.hoisted(() => ({
  addPulseLine: vi.fn(),
  update: vi.fn(),
  dispose: vi.fn(),
}))

const statusRingMocks = vi.hoisted(() => ({
  nodeExtension: vi.fn(),
  startAnimationLoop: vi.fn(),
  stopAnimationLoop: vi.fn(),
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

vi.mock('../../composables/useCommunicationPulse', () => ({
  useCommunicationPulse: () => pulseMocks,
}))

vi.mock('../../composables/useAgentStatusRing', () => ({
  useAgentStatusRing: () => statusRingMocks,
}))

vi.mock('../../composables/useForceGraph', async () => {
  const { ref } = await import('vue')
  return {
    useForceGraph: () => ({
      graph: ref(null),
      graphError: null,
      setFullGraph: vi.fn(),
      applyDiff: vi.fn(),
      resetCamera: vi.fn(),
      getInternalNodes: vi.fn(() => []),
    }),
  }
})

describe('SimulationPage', () => {
  beforeEach(() => {
    push.mockReset()
    window.sessionStorage.clear()
    pulseMocks.addPulseLine.mockReset()
    pulseMocks.update.mockReset()
    pulseMocks.dispose.mockReset()
    statusRingMocks.nodeExtension.mockReset()
    statusRingMocks.startAnimationLoop.mockReset()
    statusRingMocks.stopAnimationLoop.mockReset()
    apiMocks.getSimulationGraph.mockResolvedValue({ nodes: [], edges: [] })
    apiMocks.getSimulationTimeline.mockResolvedValue([])
    apiMocks.getSimulationColonies.mockResolvedValue([])
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
    expect(wrapper.text()).toContain('Society')
    expect(wrapper.text()).toContain('Colonies')
  })

  it('starts overlay animation loops and disposes them on unmount', async () => {
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

    const rafSpy = vi.spyOn(window, 'requestAnimationFrame')
    const cancelSpy = vi.spyOn(window, 'cancelAnimationFrame')
    let queuedFrame: ((time: number) => void) | null = null

    rafSpy.mockImplementation((cb: FrameRequestCallback) => {
      queuedFrame = cb
      return 42
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(statusRingMocks.startAnimationLoop).toHaveBeenCalledTimes(1)
    expect(queuedFrame).toBeTypeOf('function')

    const runQueuedFrame = queuedFrame as ((time: number) => void) | null
    runQueuedFrame?.(16)
    expect(pulseMocks.update).toHaveBeenCalledWith(0.016)

    wrapper.unmount()

    expect(statusRingMocks.stopAnimationLoop).toHaveBeenCalledTimes(1)
    expect(cancelSpy).toHaveBeenCalledWith(42)
    expect(pulseMocks.dispose).toHaveBeenCalledTimes(1)
  })
})
