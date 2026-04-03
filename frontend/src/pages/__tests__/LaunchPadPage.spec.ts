import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LaunchPadPage from '../LaunchPadPage.vue'

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getTemplates: vi.fn(),
  listSimulations: vi.fn(),
  listPopulations: vi.fn(),
  createProject: vi.fn(),
  uploadDocument: vi.fn(),
  createSimulation: vi.fn(),
}))

const scenarioPairMocks = vi.hoisted(() => ({
  createScenarioPair: vi.fn(),
  error: null as string | null,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

vi.mock('../../stores/scenarioPairStore', () => ({
  useScenarioPairStore: () => scenarioPairMocks,
}))

describe('LaunchPadPage', () => {
  beforeEach(() => {
    push.mockReset()
    scenarioPairMocks.createScenarioPair.mockReset()
    scenarioPairMocks.error = null
    apiMocks.getHealth.mockResolvedValue({
      status: 'ok',
      version: '1.0.0',
      llm_provider: 'openai',
      live_simulation_available: true,
      live_simulation_message: '',
    })
    apiMocks.getTemplates.mockResolvedValue([
      {
        id: 'tmpl-1',
        name: 'business_analysis',
        display_name: 'Business Analysis',
        description: 'desc',
        category: 'strategy',
      },
    ])
    apiMocks.listSimulations.mockResolvedValue([])
    apiMocks.listPopulations.mockResolvedValue([
      { id: 'pop-abc123', agent_count: 1000, status: 'ready' },
    ])
    apiMocks.createProject.mockResolvedValue({ id: 'project-1' })
    apiMocks.uploadDocument.mockResolvedValue({})
    apiMocks.createSimulation.mockResolvedValue({ id: 'sim-1' })
  })

  it('shows simplified input section and launches standard mode with strict evidence', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await flushPromises()

    // New simplified UI shows "何を分析しますか？" instead of old flow card
    expect(wrapper.text()).toContain('何を分析しますか？')
    expect(wrapper.text()).toContain('分析を開始')

    // Type in the free prompt textarea
    await wrapper.get('.prompt-textarea').setValue('EV battery market analysis')
    await wrapper.get('[data-testid="launch-button"]').trigger('click')
    await flushPromises()

    expect(apiMocks.createSimulation).toHaveBeenCalledWith(
      expect.objectContaining({
        evidenceMode: 'strict',
        mode: 'standard',
      }),
    )
    expect(push).toHaveBeenCalledWith('/sim/sim-1')
  })

  it('shows Japanese status label with pulse-dot for running simulations', async () => {
    apiMocks.listSimulations.mockResolvedValue([
      {
        id: 'sim-running',
        project_id: null,
        mode: 'standard',
        status: 'running',
        template_name: 'market_entry',
        execution_profile: 'standard',
        colony_count: 1,
        pipeline_stage: 'single',
        run_id: null,
        swarm_id: null,
        created_at: '2026-04-01T00:00:00Z',
        completed_at: null,
      },
      {
        id: 'sim-done',
        project_id: null,
        mode: 'standard',
        status: 'completed',
        template_name: 'policy_impact',
        execution_profile: 'standard',
        colony_count: 1,
        pipeline_stage: 'completed',
        run_id: null,
        swarm_id: null,
        created_at: '2026-03-31T00:00:00Z',
        completed_at: '2026-03-31T01:00:00Z',
      },
    ])

    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    const badges = wrapper.findAll('.status-badge')
    const runningBadge = badges.find(b => b.classes().includes('status-running'))
    expect(runningBadge).toBeDefined()
    expect(runningBadge!.text()).toBe('実行中')

    const completedBadge = badges.find(b => b.classes().includes('status-completed'))
    expect(completedBadge).toBeDefined()
    expect(completedBadge!.text()).toBe('完了')
  })

  it('highlights Standard preset card with recommended badge', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    const standardCard = wrapper.get('[data-testid="preset-standard"]')
    expect(standardCard.find('.preset-recommended').exists()).toBe(true)
    expect(standardCard.find('.preset-recommended').text()).toBe('おすすめ')
    expect(standardCard.classes()).toContain('recommended')
  })

  it('renders scenario comparison section with heading and button', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    const section = wrapper.get('[data-testid="scenario-comparison-section"]')
    expect(section.text()).toContain('シナリオ比較')
    expect(section.text()).toContain('ベースラインと政策介入を比較し、影響を可視化します')

    const button = wrapper.get('[data-testid="scenario-compare-button"]')
    expect(button.text()).toContain('シナリオ比較を開始')
  })

  it('calls createScenarioPair and navigates on scenario compare button click', async () => {
    scenarioPairMocks.createScenarioPair.mockResolvedValue({ id: 'pair-42' })

    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    // Fill in the decision context
    await wrapper.get('[data-testid="scenario-decision-context"]').setValue('住宅補助金制度の導入')

    // Click the compare button
    await wrapper.get('[data-testid="scenario-compare-button"]').trigger('click')
    await flushPromises()

    expect(scenarioPairMocks.createScenarioPair).toHaveBeenCalledWith({
      population_id: 'pop-abc123',
      decision_context: '住宅補助金制度の導入',
      intervention_params: expect.objectContaining({ policy_type: '住宅補助金' }),
      preset: 'standard',
    })
    expect(push).toHaveBeenCalledWith('/scenario/pair-42')
  })
})
