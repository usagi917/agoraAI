import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockApi),
  },
}))

async function loadClient() {
  vi.resetModules()
  return await import('../client')
}

describe('api client validation token headers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.get.mockResolvedValue({ data: {} })
    mockApi.post.mockResolvedValue({ data: { id: 'sim-1' } })
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('attaches the validation token header to validation requests when configured', async () => {
    vi.stubEnv('VITE_VALIDATION_TOKEN', 'secret123')
    const { createSimulation, getValidationReport, getValidationTopics } = await loadClient()

    await createSimulation({ diagnostic: { survey_id: 'x' } })
    await getValidationTopics('economy')
    await getValidationReport('sim-1', 'survey-1')

    expect(mockApi.post).toHaveBeenCalledWith(
      '/simulations',
      expect.objectContaining({
        diagnostic: { survey_id: 'x' },
      }),
      expect.objectContaining({
        headers: { 'X-Validation-Token': 'secret123' },
      }),
    )
    expect(mockApi.get).toHaveBeenCalledWith(
      '/validation/topics',
      expect.objectContaining({
        params: { preset: 'economy' },
        headers: { 'X-Validation-Token': 'secret123' },
      }),
    )
    expect(mockApi.get).toHaveBeenCalledWith(
      '/simulations/sim-1/validation-report',
      expect.objectContaining({
        params: { survey_id: 'survey-1' },
        headers: { 'X-Validation-Token': 'secret123' },
      }),
    )
  })

  it('does not send a validation token header when the token is unset', async () => {
    vi.stubEnv('VITE_VALIDATION_TOKEN', '')
    const { createSimulation, getValidationReport, getValidationTopics } = await loadClient()

    await createSimulation({ diagnostic: { survey_id: 'x' } })
    await getValidationTopics('economy')
    await getValidationReport('sim-1', 'survey-1')

    const simulationConfig = mockApi.post.mock.calls[0][2]
    const topicsConfig = mockApi.get.mock.calls[0][1]
    const reportConfig = mockApi.get.mock.calls[1][1]

    expect(simulationConfig).toBeUndefined()
    expect(topicsConfig).not.toHaveProperty('headers')
    expect(reportConfig).not.toHaveProperty('headers')
  })
})
