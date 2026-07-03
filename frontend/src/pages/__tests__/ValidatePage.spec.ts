import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ValidatePage from '../ValidatePage.vue'

let routeParams: Record<string, string> = {}
const push = vi.fn()

const apiMocks = vi.hoisted(() => ({
  createSimulation: vi.fn(),
  getValidationReport: vi.fn(),
  getValidationTopics: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: routeParams }),
  useRouter: () => ({ push }),
}))

vi.mock('../../api/client', () => apiMocks)

vi.mock('../../composables/useSimulationSSE', () => ({
  useSimulationSSE: () => ({
    start: vi.fn(),
    close: vi.fn(),
  }),
}))

function topic() {
  return {
    survey_id: 'survey-1',
    theme: '金利政策',
    question: '金融緩和政策を支持しますか',
    source: 'BOJ',
    survey_date: '2024-03',
    sample_size: 2182,
    source_origin: 'same_source_as_train',
    actual_distribution: {
      賛成: 0.15,
      条件付き賛成: 0.2,
      中立: 0.35,
      条件付き反対: 0.18,
      反対: 0.12,
    },
  }
}

function report() {
  return {
    simulation_id: 'sim-1',
    preset: 'economy',
    predicted: topic().actual_distribution,
    actual: topic().actual_distribution,
    jsd: 0,
    emd: 0,
    brier: 0,
    ece: 0,
    verdict: 'hit',
    sample_reasons: [{ reason: '理由', stance: '賛成' }],
    evaluations: [
      {
        survey_id: 'survey-1',
        theme: '金利政策',
        question: '',
        source: 'BOJ',
        predicted: topic().actual_distribution,
        actual: topic().actual_distribution,
        jsd: 0,
        emd: 0,
        brier: 0,
        ece: 0,
        verdict: 'hit',
      },
    ],
  }
}

describe('ValidatePage', () => {
  beforeEach(() => {
    routeParams = {}
    push.mockReset()
    apiMocks.createSimulation.mockReset()
    apiMocks.getValidationReport.mockReset()
    apiMocks.getValidationTopics.mockResolvedValue({ preset: 'economy', topics: [topic()] })
  })

  function mountPage() {
    return mount(ValidatePage, {
      global: {
        plugins: [createPinia()],
        stubs: {
          LiveSocietyGraph: { template: '<div data-testid="live-graph"></div>' },
          ValidationVerdictCard: { template: '<div data-testid="verdict-card"></div>' },
          DistributionCompare: { template: '<div data-testid="distribution-compare"></div>' },
          ConditionStrip: { template: '<div data-testid="condition-strip"></div>' },
          OpinionBubbles: { template: '<div data-testid="opinion-bubbles"></div>' },
        },
      },
    })
  }

  it('loads topics and starts validation', async () => {
    apiMocks.createSimulation.mockResolvedValue({ id: 'sim-1' })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('select').text()).toContain('金利政策')
    await wrapper.get('.run-button').trigger('click')
    await flushPromises()

    expect(apiMocks.createSimulation).toHaveBeenCalledWith(expect.objectContaining({
      promptText: '金利政策',
      diagnostic: expect.objectContaining({ survey_id: 'survey-1' }),
    }))
    expect(push).toHaveBeenCalledWith('/validate/sim-1')
  })

  it('loads report for direct links', async () => {
    routeParams = { id: 'sim-1' }
    apiMocks.getValidationReport.mockResolvedValue(report())

    const wrapper = mountPage()
    await flushPromises()

    expect(apiMocks.getValidationReport).toHaveBeenCalledWith('sim-1', 'survey-1')
    expect(wrapper.find('[data-testid="verdict-card"]').exists()).toBe(true)
  })

  it('shows retryable error when start fails', async () => {
    apiMocks.createSimulation.mockRejectedValue({ response: { data: { detail: 'busy' } } })
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('.run-button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('busy')
    expect(wrapper.text()).toContain('再試行')
  })
})
