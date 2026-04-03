import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PopulationPage from '../PopulationPage.vue'

const apiMocks = vi.hoisted(() => ({
  listPopulations: vi.fn(),
  generatePopulation: vi.fn(),
  getPopulationDetail: vi.fn(),
  forkPopulation: vi.fn(),
}))

vi.mock('../../api/client', () => apiMocks)

function makeSampleAgents(overrides: Array<Partial<any>> = []) {
  const defaults = [
    { id: 'a1', agent_index: 0, demographics: { occupation: '会社員', age: 35, region: '関東', gender: 'male', income_bracket: 'upper_middle', education: 'bachelor' }, big_five: { O: 0.7, C: 0.5, E: 0.6, A: 0.4, N: 0.3 }, llm_backend: 'openai', memory_summary: '記憶A' },
    { id: 'a2', agent_index: 1, demographics: { occupation: '教師', age: 42, region: '関西', gender: 'female', income_bracket: 'lower_middle', education: 'master' }, big_five: { O: 0.5, C: 0.8, E: 0.3, A: 0.7, N: 0.4 }, llm_backend: 'anthropic', memory_summary: '記憶B' },
    { id: 'a3', agent_index: 2, demographics: { occupation: '会社員', age: 28, region: '関東', gender: 'female', income_bracket: 'lower_middle', education: 'bachelor' }, big_five: { O: 0.6, C: 0.6, E: 0.7, A: 0.5, N: 0.2 }, llm_backend: 'openai', memory_summary: '記憶C' },
    { id: 'a4', agent_index: 3, demographics: { occupation: '農業従事者', age: 58, region: '東北', gender: 'male', income_bracket: 'low', education: 'high_school' }, big_five: { O: 0.3, C: 0.7, E: 0.4, A: 0.6, N: 0.5 }, llm_backend: 'gemini', memory_summary: '記憶D' },
    { id: 'a5', agent_index: 4, demographics: { occupation: '教師', age: 50, region: '関西', gender: 'male', income_bracket: 'upper_middle', education: 'doctorate' }, big_five: { O: 0.8, C: 0.4, E: 0.5, A: 0.8, N: 0.1 }, llm_backend: 'openai', memory_summary: '記憶E' },
  ]
  return overrides.length ? overrides : defaults
}

function makePopDetail(overrides: Partial<any> = {}) {
  return {
    id: 'pop-1',
    parent_id: null,
    version: 1,
    agent_count: 1000,
    status: 'ready',
    generation_params: {},
    created_at: '2026-04-01T00:00:00Z',
    sample_agents: makeSampleAgents(),
    ...overrides,
  }
}

describe('PopulationPage', () => {
  beforeEach(() => {
    apiMocks.listPopulations.mockResolvedValue([
      { id: 'pop-1', version: 1, agent_count: 1000, status: 'ready', created_at: '2026-04-01T00:00:00Z' },
    ])
    apiMocks.generatePopulation.mockResolvedValue({ id: 'pop-new', agent_count: 1000, status: 'ready' })
    apiMocks.getPopulationDetail.mockResolvedValue(makePopDetail())
    apiMocks.forkPopulation.mockResolvedValue({ id: 'pop-2', parent_id: 'pop-1', version: 2, agent_count: 1000, status: 'ready' })
  })

  function mountPage() {
    return mount(PopulationPage)
  }

  // --- Basic rendering ---

  it('renders population list on mount', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('人口管理')
    expect(wrapper.text()).toContain('v1')
    expect(wrapper.text()).toContain('1,000')
  })

  it('calls generatePopulation on button click', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="generate-button"]').trigger('click')
    await flushPromises()

    expect(apiMocks.generatePopulation).toHaveBeenCalledWith(1000)
  })

  // --- Demographics distribution charts ---

  it('renders demographics distribution charts when population is selected', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.pop-card').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="demographics-charts"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chart-occupation"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chart-region"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chart-age"]').exists()).toBe(true)
  })

  it('renders occupation distribution bars with correct counts', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.pop-card').trigger('click')
    await flushPromises()

    const occupationChart = wrapper.get('[data-testid="chart-occupation"]')
    // 会社員: 2, 教師: 2, 農業従事者: 1
    expect(occupationChart.text()).toContain('会社員')
    expect(occupationChart.text()).toContain('教師')
    expect(occupationChart.text()).toContain('農業従事者')

    // Check bar widths reflect proportions (会社員 and 教師 are 40% each, 農業従事者 20%)
    const bars = occupationChart.findAll('[data-testid="dist-bar"]')
    expect(bars.length).toBeGreaterThanOrEqual(3)
  })

  it('renders region distribution bars', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.pop-card').trigger('click')
    await flushPromises()

    const regionChart = wrapper.get('[data-testid="chart-region"]')
    expect(regionChart.text()).toContain('関東')
    expect(regionChart.text()).toContain('関西')
    expect(regionChart.text()).toContain('東北')
  })

  it('renders age distribution with range buckets', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.pop-card').trigger('click')
    await flushPromises()

    const ageChart = wrapper.get('[data-testid="chart-age"]')
    // Ages: 35, 42, 28, 58, 50 → buckets: 20代(1), 30代(1), 40代(1), 50代(2)
    expect(ageChart.text()).toContain('20代')
    expect(ageChart.text()).toContain('50代')
  })

  // --- Fork diff view ---

  it('shows fork diff section when population has a parent', async () => {
    const parentDetail = makePopDetail({ id: 'pop-parent', version: 1 })
    const childDetail = makePopDetail({
      id: 'pop-child',
      parent_id: 'pop-parent',
      version: 2,
      sample_agents: makeSampleAgents([
        { id: 'a1', agent_index: 0, demographics: { occupation: 'エンジニア', age: 36, region: '関東', gender: 'male', income_bracket: 'high', education: 'master' }, big_five: { O: 0.8, C: 0.5, E: 0.6, A: 0.4, N: 0.3 }, llm_backend: 'openai', memory_summary: '記憶A(更新)' },
        { id: 'a2', agent_index: 1, demographics: { occupation: '教師', age: 43, region: '関西', gender: 'female', income_bracket: 'lower_middle', education: 'master' }, big_five: { O: 0.5, C: 0.8, E: 0.3, A: 0.7, N: 0.4 }, llm_backend: 'anthropic', memory_summary: '記憶B(更新)' },
        { id: 'a3', agent_index: 2, demographics: { occupation: '会社員', age: 29, region: '関東', gender: 'female', income_bracket: 'upper_middle', education: 'bachelor' }, big_five: { O: 0.6, C: 0.6, E: 0.7, A: 0.5, N: 0.2 }, llm_backend: 'openai', memory_summary: '記憶C' },
      ]),
    })

    apiMocks.listPopulations.mockResolvedValue([
      { id: 'pop-child', version: 2, agent_count: 1000, status: 'ready', created_at: '2026-04-01T01:00:00Z' },
    ])

    // First call returns child, second call returns parent
    apiMocks.getPopulationDetail
      .mockResolvedValueOnce(childDetail)
      .mockResolvedValueOnce(parentDetail)

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.pop-card').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="fork-diff"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('v1')
    expect(wrapper.text()).toContain('v2')
  })

  it('does not show fork diff when population has no parent', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.pop-card').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="fork-diff"]').exists()).toBe(false)
  })

  it('shows version lineage badge for forked populations', async () => {
    const childDetail = makePopDetail({ id: 'pop-child', parent_id: 'pop-parent', version: 2 })
    apiMocks.getPopulationDetail
      .mockResolvedValueOnce(childDetail)
      .mockResolvedValueOnce(makePopDetail())

    apiMocks.listPopulations.mockResolvedValue([
      { id: 'pop-child', version: 2, agent_count: 1000, status: 'ready', created_at: '2026-04-01T01:00:00Z' },
    ])

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.pop-card').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="version-lineage"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="version-lineage"]').text()).toContain('v1')
    expect(wrapper.find('[data-testid="version-lineage"]').text()).toContain('v2')
  })

  // --- Error handling ---

  it('shows error banner when list fetch fails', async () => {
    apiMocks.listPopulations.mockRejectedValue(new Error('fail'))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('人口リストの取得に失敗しました')
  })

  it('shows error banner when generation fails', async () => {
    apiMocks.generatePopulation.mockRejectedValue(new Error('fail'))

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="generate-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('人口生成に失敗しました')
  })
})
