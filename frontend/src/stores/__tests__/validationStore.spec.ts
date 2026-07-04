import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useValidationStore } from '../validationStore'

const apiMocks = vi.hoisted(() => ({
  createSimulation: vi.fn(),
  getValidationReport: vi.fn(),
  getValidationTopics: vi.fn(),
}))

vi.mock('../../api/client', () => apiMocks)

describe('validationStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMocks.createSimulation.mockReset()
    apiMocks.getValidationReport.mockReset()
    apiMocks.getValidationTopics.mockReset()
  })

  it('loads topics and selects the first topic', async () => {
    apiMocks.getValidationTopics.mockResolvedValue({
      preset: 'economy',
      topics: [
        {
          survey_id: 's1',
          theme: '金利政策',
          question: '',
          source: 'source',
          survey_date: '2024-03',
          sample_size: 1,
          actual_distribution: {},
        },
      ],
    })
    const store = useValidationStore()

    await store.loadTopics()

    expect(store.selectedSurveyId).toBe('s1')
    expect(store.selectedTopic?.theme).toBe('金利政策')
  })

  it('starts validation with diagnostic payload', async () => {
    apiMocks.getValidationTopics.mockResolvedValue({
      preset: 'economy',
      topics: [
        {
          survey_id: 's1',
          theme: '金利政策',
          question: '',
          source: 'source',
          survey_date: '2024-03',
          sample_size: 1,
          actual_distribution: {},
        },
      ],
    })
    apiMocks.createSimulation.mockResolvedValue({ id: 'sim-1' })
    const store = useValidationStore()
    await store.loadTopics()

    const simId = await store.startValidation(42)

    expect(simId).toBe('sim-1')
    expect(apiMocks.createSimulation).toHaveBeenCalledWith(expect.objectContaining({
      promptText: '金利政策',
      seed: 42,
      diagnostic: expect.objectContaining({
        survey_id: 's1',
        stop_after: 'society_pulse',
      }),
    }))
  })
})
