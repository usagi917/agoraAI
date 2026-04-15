import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentStory } from '../useAgentStory'
import { useSocietyGraphStore } from '../../stores/societyGraphStore'
import type { AgentDetailResponse, MeetingArgument } from '../../api/client'

// Mock the API client
const mockGetAgentDetail = vi.fn()
vi.mock('../../api/client', () => ({
  getAgentDetail: (...args: any[]) => mockGetAgentDetail(...args),
}))

function makeMeetingArg(overrides: Partial<MeetingArgument> = {}): MeetingArgument {
  return {
    participant_index: 0,
    participant_name: 'Agent A',
    role: 'citizen',
    expertise: 'general',
    round: 1,
    position: 'support',
    argument: 'Test argument',
    evidence: '',
    concerns: [],
    questions_to_others: [],
    ...overrides,
  }
}

function makeAgentDetail(overrides: Partial<AgentDetailResponse> = {}): AgentDetailResponse {
  return {
    id: 'agent-1',
    agent_index: 0,
    population_id: 'pop-1',
    demographics: { age: 30, gender: 'M', occupation: '会社員', region: '東京', income_bracket: '中', education: '大学' },
    big_five: { O: 0.5, C: 0.5, E: 0.5, A: 0.5, N: 0.5 },
    values: {},
    life_event: '',
    contradiction: '',
    information_source: '',
    local_context: '',
    hidden_motivation: '',
    speech_style: '',
    shock_sensitivity: {},
    memory_summary: '',
    activation_response: null,
    meeting_participant: null,
    meeting_contributions: [],
    connections: [],
    ...overrides,
  }
}

describe('useAgentStory', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGetAgentDetail.mockReset()
  })

  it('agentId 変更時に fetchDetail が呼ばれる', async () => {
    const detail = makeAgentDetail()
    mockGetAgentDetail.mockResolvedValue(detail)

    const agentId = ref<string | null>(null)
    const { agentDetail } = useAgentStory('sim-1', agentId)

    agentId.value = 'agent-1'
    await nextTick()
    // Wait for the async fetchDetail to complete
    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(1))

    expect(mockGetAgentDetail).toHaveBeenCalledWith('sim-1', 'agent-1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(agentDetail.value).toEqual(detail)
  })

  it('agentId=null 時に agentDetail がクリアされる', async () => {
    const detail = makeAgentDetail()
    mockGetAgentDetail.mockResolvedValue(detail)

    const agentId = ref<string | null>('agent-1')
    const { agentDetail } = useAgentStory('sim-1', agentId)

    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(1))
    expect(agentDetail.value).not.toBeNull()

    agentId.value = null
    await nextTick()
    expect(agentDetail.value).toBeNull()
  })

  it('opinionJourney: contribution と stance_shift のマッピングが正しい', async () => {
    const contributions: MeetingArgument[] = [
      makeMeetingArg({ round: 1, argument: 'First point', belief_update: 'Changed my mind' }),
      makeMeetingArg({ round: 2, argument: 'Second point', addressed_to: 'Agent B', round_name: 'Round 2' }),
    ]
    const detail = makeAgentDetail({ meeting_contributions: contributions })
    mockGetAgentDetail.mockResolvedValue(detail)

    const agentId = ref<string | null>('agent-1')
    const { opinionJourney } = useAgentStory('sim-1', agentId)

    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(1))

    const items = opinionJourney.value
    // Round 1: contribution + stance_shift, Round 2: contribution only
    expect(items).toHaveLength(3)
    expect(items[0]).toMatchObject({ type: 'contribution', round: 1, content: 'First point' })
    expect(items[1]).toMatchObject({ type: 'stance_shift', round: 1, content: 'Changed my mind' })
    expect(items[2]).toMatchObject({ type: 'contribution', round: 2, content: 'Second point', addressedTo: 'Agent B', roundName: 'Round 2' })
  })

  it('opinionJourney: agentDetail=null なら空配列', () => {
    const agentId = ref<string | null>(null)
    const { opinionJourney } = useAgentStory('sim-1', agentId)
    expect(opinionJourney.value).toEqual([])
  })

  it('influenceMap: 重複除去、カウント降順ソート、5件スライス', async () => {
    // Create contributions addressed to 7 different agents, with varying counts
    const contributions: MeetingArgument[] = [
      makeMeetingArg({ addressed_to: 'A' }),
      makeMeetingArg({ addressed_to: 'A' }),
      makeMeetingArg({ addressed_to: 'A' }),
      makeMeetingArg({ addressed_to: 'B' }),
      makeMeetingArg({ addressed_to: 'B' }),
      makeMeetingArg({ addressed_to: 'C' }),
      makeMeetingArg({ addressed_to: 'C' }),
      makeMeetingArg({ addressed_to: 'D' }),
      makeMeetingArg({ addressed_to: 'E' }),
      makeMeetingArg({ addressed_to: 'F' }),
      makeMeetingArg({ addressed_to: 'G' }),
    ]
    const detail = makeAgentDetail({ meeting_contributions: contributions })
    mockGetAgentDetail.mockResolvedValue(detail)

    const agentId = ref<string | null>('agent-1')
    const { influenceMap } = useAgentStory('sim-1', agentId)

    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(1))

    const map = influenceMap.value
    expect(map).toHaveLength(5) // sliced to 5
    expect(map[0]).toEqual({ agentName: 'A', count: 3 }) // highest count first
    expect(map[1]).toEqual({ agentName: 'B', count: 2 })
    expect(map[2]).toEqual({ agentName: 'C', count: 2 })
  })

  it('ラウンド変化で同一エージェントなら再フェッチする', async () => {
    const detail = makeAgentDetail()
    mockGetAgentDetail.mockResolvedValue(detail)

    const agentId = ref<string | null>('agent-1')
    useAgentStory('sim-1', agentId)

    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(1))

    // Simulate round change
    const store = useSocietyGraphStore()
    store.currentRound = 2
    await nextTick()

    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(2))
  })

  it('リクエスト競合時に abort された側が loading を false にしない', async () => {
    let resolveFirst: (v: AgentDetailResponse) => void
    const firstPromise = new Promise<AgentDetailResponse>((r) => { resolveFirst = r })
    const secondDetail = makeAgentDetail({ id: 'agent-2' })

    mockGetAgentDetail.mockImplementationOnce(() => firstPromise)
    mockGetAgentDetail.mockImplementationOnce(() => Promise.resolve(secondDetail))

    const agentId = ref<string | null>('agent-1')
    const { loading } = useAgentStory('sim-1', agentId)

    await nextTick()
    expect(loading.value).toBe(true)

    // Trigger second request while first is still in flight
    agentId.value = 'agent-2'
    await nextTick()

    // First request is now aborted — resolve it to trigger finally
    resolveFirst!(makeAgentDetail({ id: 'agent-1' }))
    await nextTick()

    // Wait for second request to complete
    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(2))

    // loading should be false only after the second (latest) request completes
    expect(loading.value).toBe(false)
  })

  it('ラウンド変化で異なるエージェント（lastFetchedId と不一致）なら再フェッチしない', async () => {
    const detail = makeAgentDetail({ id: 'agent-1' })
    mockGetAgentDetail.mockResolvedValue(detail)

    const agentId = ref<string | null>('agent-1')
    useAgentStory('sim-1', agentId)

    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(1))

    // Change agentId to a new agent — this triggers the agentId watcher (fetch #2)
    agentId.value = 'agent-2'
    await nextTick()
    await vi.waitFor(() => expect(mockGetAgentDetail).toHaveBeenCalledTimes(2))

    // Now change round — lastFetchedId is 'agent-2' (set by the mock resolve)
    // but we want to test when lastFetchedId != agentId.value
    // Reset and set up so lastFetchedId stays stale
    mockGetAgentDetail.mockReset()
    mockGetAgentDetail.mockImplementation(() => new Promise(() => {})) // never resolves

    agentId.value = 'agent-3' // triggers fetch but never completes → lastFetchedId stays 'agent-2'
    await nextTick()

    const callCountAfterAgentChange = mockGetAgentDetail.mock.calls.length

    // Round change: agentId.value='agent-3' but lastFetchedId='agent-2' → no re-fetch
    const store = useSocietyGraphStore()
    store.currentRound = 5
    await nextTick()

    // Should not have increased
    expect(mockGetAgentDetail).toHaveBeenCalledTimes(callCountAfterAgentChange)
  })
})
