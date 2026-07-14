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

describe('LaunchPadPage', () => {
  beforeEach(() => {
    push.mockReset()
    apiMocks.getHealth.mockReset()
    apiMocks.getTemplates.mockReset()
    apiMocks.listSimulations.mockReset()
    apiMocks.createProject.mockReset()
    apiMocks.uploadDocument.mockReset()
    apiMocks.createSimulation.mockReset()
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
        inputMethod: 'manual',
        mode: 'standard',
      }),
    )
    expect(push).toHaveBeenCalledWith('/sim/sim-1')
  })

  it('does not expose or fetch simulation history on the launchpad', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('実行履歴')
    expect(wrapper.find('.history-details').exists()).toBe(false)
    expect(apiMocks.listSimulations).not.toHaveBeenCalled()
  })

  it('discloses anonymous usage and input logging before launch', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    const notice = wrapper.get('[data-testid="usage-logging-notice"]')
    expect(notice.text()).toContain('アクセス情報・匿名の利用状況・入力内容を記録')
    expect(notice.text()).toContain('個人情報や機密情報は入力しないでください')
  })

  it('shows exactly one completed analysis example linking to its result', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: {
        stubs: {
          RouterLink: {
            props: ['to'],
            template: '<a :href="to"><slot /></a>',
          },
        },
      },
    })
    await flushPromises()

    const examples = wrapper.findAll('[data-testid="featured-example-card"]')
    expect(examples).toHaveLength(1)
    expect(examples[0].text()).toContain('食生活改善サブスク')
    expect(examples[0].text()).toContain('想定顧客へのインタビュー形式')
    expect(examples[0].text()).toContain('分析完了')
    expect(examples[0].attributes('href')).toBe(
      '/sim/db6bbd23-d31c-461c-8e18-6398a44bd4b9/results',
    )
  })

  it('keeps the launch button clickable-state stable while a launch is pending', async () => {
    let resolveSimulation!: (value: { id: string }) => void
    const pendingSimulation = new Promise<{ id: string }>((resolve) => {
      resolveSimulation = resolve
    })
    apiMocks.createSimulation.mockReturnValueOnce(pendingSimulation)

    const wrapper = mount(LaunchPadPage, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    await flushPromises()
    await wrapper.get('.prompt-textarea').setValue('EV battery market analysis')

    const launchButton = wrapper.get('[data-testid="launch-button"]')
    await launchButton.trigger('click')
    await flushPromises()

    expect(apiMocks.createSimulation).toHaveBeenCalledTimes(1)
    expect(launchButton.attributes('disabled')).toBeUndefined()

    await launchButton.trigger('click')
    await flushPromises()

    expect(apiMocks.createSimulation).toHaveBeenCalledTimes(1)

    resolveSimulation({ id: 'sim-1' })
    await flushPromises()

    expect(push).toHaveBeenCalledWith('/sim/sim-1')
  })

  it('highlights Standard preset card with recommended badge', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    const advancedDetails = wrapper.get('.advanced-details')
    ;(advancedDetails.element as HTMLDetailsElement).open = true
    await advancedDetails.trigger('toggle')
    await flushPromises()

    const standardCard = wrapper.get('[data-testid="preset-standard"]')
    expect(standardCard.find('.preset-recommended').exists()).toBe(true)
    expect(standardCard.find('.preset-recommended').text()).toBe('おすすめ')
    expect(standardCard.classes()).toContain('recommended')
  })

  it('does not render scenario comparison section on the launchpad', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="scenario-comparison-section"]').exists()).toBe(false)
  })

  it('describes the current preset-aware analysis workflow', async () => {
    const wrapper = mount(LaunchPadPage, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    const workflow = wrapper.get('.phase-workflow').text()
    expect(workflow).toContain('根拠文書を添付')
    expect(workflow).toContain('デジタル住民たち')
    expect(workflow).toContain('標準は代表評議会')
    expect(workflow).toContain('検証強化は論点抽出と介入比較')
    expect(workflow).toContain('進捗をリアルタイムに可視化')
  })
})
