import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LaunchPadPage from '../LaunchPadPage.vue'

const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getTemplates: vi.fn(),
  listSimulations: vi.fn(),
  createProject: vi.fn(),
  uploadDocument: vi.fn(),
  createSimulation: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

describe('LaunchPadPage — template-specific wizard steps', () => {
  beforeEach(() => {
    push.mockReset()
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
        name: 'market_entry',
        display_name: '市場参入判断',
        description: '新市場への参入判断',
        category: 'ビジネス',
      },
      {
        id: 'tmpl-2',
        name: 'policy_impact',
        display_name: '政策影響シミュレーション',
        description: '政策導入の影響',
        category: '政策',
      },
    ])
    apiMocks.listSimulations.mockResolvedValue([])
    apiMocks.createSimulation.mockResolvedValue({ id: 'sim-1' })
  })

  function mountPage() {
    return mount(LaunchPadPage, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
  }

  it('auto-selects matching backend template when question template is chosen', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="question-market_entry"]').trigger('click')

    // Fill wizard steps
    const inputs = wrapper.findAll('.wizard-input')
    for (const input of inputs) {
      await input.setValue('テスト入力')
    }

    await wrapper.get('[data-testid="launch-button"]').trigger('click')
    await flushPromises()

    expect(apiMocks.createSimulation).toHaveBeenCalledWith(
      expect.objectContaining({
        templateName: 'market_entry',
      }),
    )
  })

  it('uses policy_impact template when policy question is selected', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="question-policy_impact"]').trigger('click')

    const inputs = wrapper.findAll('.wizard-input')
    for (const input of inputs) {
      await input.setValue('テスト入力')
    }

    await wrapper.get('[data-testid="launch-button"]').trigger('click')
    await flushPromises()

    expect(apiMocks.createSimulation).toHaveBeenCalledWith(
      expect.objectContaining({
        templateName: 'policy_impact',
      }),
    )
  })

  it('renders simplified unified input section', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('何を分析しますか？')
    expect(wrapper.text()).toContain('分析を開始')
  })

  it('shows wizard steps specific to the selected question template', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="question-market_entry"]').trigger('click')

    expect(wrapper.text()).toContain('業界・市場')
    expect(wrapper.text()).toContain('自社の強み・制約')
  })

  it('shows different wizard steps for policy_impact template', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="question-policy_impact"]').trigger('click')

    expect(wrapper.text()).toContain('政策の概要')
    expect(wrapper.text()).toContain('対象地域・層')
  })
})
