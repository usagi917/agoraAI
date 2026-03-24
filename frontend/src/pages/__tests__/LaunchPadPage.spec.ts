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

  it('shows simplified input section and launches unified mode with strict evidence', async () => {
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
        mode: 'unified',
      }),
    )
    expect(push).toHaveBeenCalledWith('/sim/sim-1')
  })
})
