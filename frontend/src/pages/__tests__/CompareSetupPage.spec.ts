import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CompareSetupPage from '../CompareSetupPage.vue'

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  listPopulations: vi.fn(),
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

function mountPage() {
  return mount(CompareSetupPage, {
    global: {
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

describe('CompareSetupPage', () => {
  beforeEach(() => {
    push.mockReset()
    scenarioPairMocks.createScenarioPair.mockReset()
    scenarioPairMocks.error = null
    apiMocks.listPopulations.mockResolvedValue([
      { id: 'pop-abc123', agent_count: 1000, status: 'ready' },
      { id: 'pop-def456', agent_count: 500, status: 'ready' },
    ])
  })

  it('renders the page title and description', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('シナリオ比較')
    expect(wrapper.text()).toContain('ベースラインと政策介入を比較し')
  })

  it('shows the submit button', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const btn = wrapper.get('[data-testid="compare-submit-button"]')
    expect(btn.text()).toContain('シナリオ比較を開始')
  })

  it('shows structured intervention parameter fields instead of JSON textarea', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[data-testid="compare-policy-type"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="compare-amount"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="compare-target-population"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="compare-duration"]').exists()).toBe(true)
  })

  it('populates the population select from API', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const select = wrapper.get('[data-testid="compare-population-select"]')
    const options = select.findAll('option')
    expect(options).toHaveLength(2)
    expect(options[0].text()).toContain('pop-abc1')
    expect(options[0].text()).toContain('1000人')
  })

  it('shows an empty-state message when no populations exist', async () => {
    apiMocks.listPopulations.mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('母集団がありません')
    expect(wrapper.find('[data-testid="compare-submit-button"]').exists()).toBe(false)
  })

  it('hides the form when population loading fails', async () => {
    apiMocks.listPopulations.mockRejectedValue(new Error('load failed'))
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('母集団の取得に失敗しました')
    expect(wrapper.find('[data-testid="compare-submit-button"]').exists()).toBe(false)
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('shows a validation error when decision context is empty', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="compare-error"]').text()).toContain('政策の説明を入力してください')
    expect(scenarioPairMocks.createScenarioPair).not.toHaveBeenCalled()
  })

  it('calls createScenarioPair with structured params and navigates on success', async () => {
    scenarioPairMocks.createScenarioPair.mockResolvedValue({ id: 'pair-99' })

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="compare-preset-deep"]').trigger('click')
    await wrapper.get('[data-testid="compare-decision-context"]').setValue('住宅補助金制度の導入')
    await wrapper.get('[data-testid="compare-policy-type"]').setValue('住宅補助金')
    await wrapper.get('[data-testid="compare-amount"]').setValue('月3万円')
    await wrapper.get('[data-testid="compare-target-population"]').setValue('年収400万円以下')
    await wrapper.get('[data-testid="compare-duration"]').setValue('12ヶ月')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(scenarioPairMocks.createScenarioPair).toHaveBeenCalledWith({
      population_id: 'pop-abc123',
      decision_context: '住宅補助金制度の導入',
      intervention_params: {
        policy_type: '住宅補助金',
        amount: '月3万円',
        target_population: '年収400万円以下',
        duration: '12ヶ月',
      },
      preset: 'deep',
    })
    expect(push).toHaveBeenCalledWith('/scenario/pair-99')
  })

  it('shows error from store when createScenarioPair fails', async () => {
    scenarioPairMocks.createScenarioPair.mockRejectedValue(new Error('API error'))
    scenarioPairMocks.error = 'サーバーエラーが発生しました'

    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="compare-decision-context"]').setValue('テスト政策')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="compare-error"]').text()).toContain('サーバーエラーが発生しました')
    expect(push).not.toHaveBeenCalled()
  })
})
