import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const apiMocks = vi.hoisted(() => ({
  getPopulationNetwork: vi.fn(),
}))

vi.mock('../../api/client', () => apiMocks)

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {}
  onerror: (() => void) | null = null
  readyState = 1
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: (e: MessageEvent) => void) {
    if (!this.listeners[type]) this.listeners[type] = []
    this.listeners[type].push(listener)
  }

  close() {
    this.closed = true
    this.readyState = 2
  }

  // Helper to emit events in tests
  emit(type: string, payload: Record<string, any>) {
    const data = JSON.stringify({ event_type: type, payload })
    for (const listener of this.listeners[type] || []) {
      listener(new MessageEvent(type, { data }))
    }
  }

  triggerError() {
    if (this.onerror) this.onerror()
  }
}

vi.stubGlobal('EventSource', MockEventSource)

// Mock Notification API
const mockNotification = vi.fn()
vi.stubGlobal('Notification', Object.assign(mockNotification, {
  permission: 'granted',
  requestPermission: vi.fn().mockResolvedValue('granted'),
}))

describe('useSimulationSSE', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    MockEventSource.instances = []
    apiMocks.getPopulationNetwork.mockReset()
    mockNotification.mockClear()
    ;(Notification as any).permission = 'granted'
    ;(Notification.requestPermission as ReturnType<typeof vi.fn>).mockClear()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // Helper to import fresh module each time (avoid stale closure)
  async function createSSE(simulationId = 'test-sim-1') {
    const mod = await import('../useSimulationSSE')
    return mod.useSimulationSSE(simulationId)
  }

  describe('C1: Browser Notification on simulation_completed', () => {
    it('sends browser notification when simulation completes', async () => {
      const { start } = await createSSE()
      start()

      const source = MockEventSource.instances[MockEventSource.instances.length - 1]
      source.emit('simulation_completed', {})

      expect(mockNotification).toHaveBeenCalledWith(
        expect.stringContaining('完了'),
        expect.objectContaining({ body: expect.any(String) }),
      )
    })

    it('does not send notification when permission is denied', async () => {
      ;(Notification as any).permission = 'denied'

      const { start } = await createSSE()
      start()

      const source = MockEventSource.instances[MockEventSource.instances.length - 1]
      source.emit('simulation_completed', {})

      expect(mockNotification).not.toHaveBeenCalled()
    })
  })

  describe('C2: SSE reconnection with exponential backoff', () => {
    it('reconnects on error up to 3 times', async () => {
      const { start } = await createSSE()
      start()
      expect(MockEventSource.instances).toHaveLength(1)

      // First error → reconnect after 1s
      MockEventSource.instances[0].triggerError()
      expect(MockEventSource.instances[0].closed).toBe(true)
      vi.advanceTimersByTime(1000)
      expect(MockEventSource.instances).toHaveLength(2)

      // Second error → reconnect after 2s
      MockEventSource.instances[1].triggerError()
      expect(MockEventSource.instances[1].closed).toBe(true)
      vi.advanceTimersByTime(2000)
      expect(MockEventSource.instances).toHaveLength(3)

      // Third error → reconnect after 4s
      MockEventSource.instances[2].triggerError()
      expect(MockEventSource.instances[2].closed).toBe(true)
      vi.advanceTimersByTime(4000)
      expect(MockEventSource.instances).toHaveLength(4)

      // Fourth error → no more reconnects
      MockEventSource.instances[3].triggerError()
      expect(MockEventSource.instances[3].closed).toBe(true)
      vi.advanceTimersByTime(10000)
      expect(MockEventSource.instances).toHaveLength(4)
    })

    it('does not reconnect when status is completed', async () => {
      const { useSimulationStore } = await import('../../stores/simulationStore')
      const store = useSimulationStore()

      const { start } = await createSSE()
      start()

      store.setStatus('completed')
      MockEventSource.instances[0].triggerError()
      vi.advanceTimersByTime(5000)
      expect(MockEventSource.instances).toHaveLength(1)
    })
  })

  describe('simulation failure handling', () => {
    it('leaves the loading state and closes the stream on simulation_failed', async () => {
      const { useSimulationStore } = await import('../../stores/simulationStore')
      const store = useSimulationStore()
      store.setStatus('running')

      const { start } = await createSSE()
      start()
      const source = MockEventSource.instances[MockEventSource.instances.length - 1]

      source.emit('simulation_failed', { error: '人口データの作成に失敗しました' })

      expect(store.status).toBe('failed')
      expect(store.error).toBe('人口データの作成に失敗しました')
      expect(source.closed).toBe(true)
    })
  })

  describe('全人口伝播 (population propagation) handling', () => {
    it('全員活性化と表示上限を選抜と誤表示しない', async () => {
      const { useAgentVisualizationStore } = await import('../../stores/agentVisualizationStore')
      const visualization = useAgentVisualizationStore()
      const { start } = await createSSE()
      start()
      const source = MockEventSource.instances[MockEventSource.instances.length - 1]

      source.emit('society_selection_completed', {
        total_population: 10_000,
        selected_count: 10_000,
        activated_target_count: 10_000,
        visualized_count: 200,
        selected_agents: [],
      })

      const event = visualization.systemEvents.at(-1)
      expect(event?.label).toBe('住民活性化対象')
      expect(event?.detail).toContain('全10,000人を活性化')
      expect(event?.detail).toContain('グラフ表示200人')
    })

    it('population_voice を feedEntries に混流する', async () => {
      const { useSocietyGraphStore } = await import('../../stores/societyGraphStore')
      const graph = useSocietyGraphStore()
      const { start } = await createSSE()
      start()
      const source = MockEventSource.instances[MockEventSource.instances.length - 1]
      expect(source.listeners.population_voice).toHaveLength(1)

      source.emit('population_voice', {
        round: 2,
        voices: [{
          agent_id: 'citizen-3',
          agent_index: 3,
          comment: '地域の声も反映してほしい。',
          stance: '条件付き賛成',
          prev_stance: null,
          occupation: '自営業',
          age_bracket: '50代',
        }],
      })

      expect(graph.feedEntries).toContainEqual(expect.objectContaining({
        kind: 'population_voice',
        round: 2,
        agent_id: 'citizen-3',
        comment: '地域の声も反映してほしい。',
      }))
    })

    it('population_propagation_started の古い取得結果は reset 後に適用しない', async () => {
      const { useSocietyGraphStore } = await import('../../stores/societyGraphStore')
      const graph = useSocietyGraphStore()
      graph.setSelectedAgents([
        { id: 'sel-0', agent_index: 0, name: 'A0', occupation: '会社員', age: 30, region: '関東' },
      ])

      let resolveNetwork: (value: {
        population_id: string
        node_count: number
        edge_count: number
        nodes: Array<{ id: string; agent_index: number }>
        edges: Array<[number, number, number]>
      }) => void = () => undefined
      apiMocks.getPopulationNetwork.mockReturnValueOnce(new Promise((resolve) => {
        resolveNetwork = resolve
      }))

      const { start } = await createSSE('sim-old')
      start()
      const source = MockEventSource.instances[MockEventSource.instances.length - 1]

      source.emit('population_propagation_started', { population_count: 1, edge_count: 0 })
      expect(apiMocks.getPopulationNetwork).toHaveBeenCalledWith('sim-old', expect.any(Object))

      graph.reset()
      resolveNetwork({
        population_id: 'stale-pop',
        node_count: 1,
        edge_count: 0,
        nodes: [{ id: 'pop-stale', agent_index: 1 }],
        edges: [],
      })
      await Promise.resolve()
      await Promise.resolve()

      expect(graph.populationNodeCount).toBe(0)
      expect(graph.graphNodes).toHaveLength(0)
    })

    it('population_propagation_round が societyGraphStore へ波を適用する', async () => {
      const { useSocietyGraphStore } = await import('../../stores/societyGraphStore')
      const graph = useSocietyGraphStore()
      graph.setSelectedAgents([
        { id: 'sel-0', agent_index: 0, name: 'A0', occupation: '会社員', age: 30, region: '関東' },
      ])
      graph.setPopulationNetwork({
        population_id: 'pop-1',
        node_count: 2,
        edge_count: 1,
        nodes: [
          { id: 'sel-0', agent_index: 0 },
          { id: 'pop-1-a', agent_index: 1 },
        ],
        edges: [[0, 1, 0.8]],
      })

      const { start } = await createSSE()
      start()
      const source = MockEventSource.instances[MockEventSource.instances.length - 1]
      expect(source.listeners.population_propagation_round).toHaveLength(1)

      source.emit('population_propagation_round', { changes: [{ i: 1, s: '条件付き賛成' }] })

      const popNode = graph.graphNodes.find((n) => n.id === 'pop-1-a')
      expect(popNode?.stance).toBe('条件付き賛成')
    })

    it('population_propagation_completed が分布反映と完了ログを行う', async () => {
      const { useSimulationStore } = await import('../../stores/simulationStore')
      const { useActivityStore } = await import('../../stores/activityStore')
      const store = useSimulationStore()
      const activity = useActivityStore()

      const { start } = await createSSE()
      start()
      const source = MockEventSource.instances[MockEventSource.instances.length - 1]

      source.emit('population_propagation_completed', {
        distribution: { 賛成: 0.6, 反対: 0.4 },
        total_rounds: 5,
        converged: true,
        changed_total: 12,
      })

      expect(store.opinionDistribution).toEqual({ 賛成: 0.6, 反対: 0.4 })
      expect(
        activity.entries.some((e) => e.message.includes('全人口伝播完了')),
      ).toBe(true)
    })
  })

  describe('report_completed handling', () => {
    it('registers and handles report completion once', async () => {
      const { useSimulationStore } = await import('../../stores/simulationStore')
      const { useActivityStore } = await import('../../stores/activityStore')
      const store = useSimulationStore()
      const activity = useActivityStore()

      const { start } = await createSSE()
      start()

      const source = MockEventSource.instances[MockEventSource.instances.length - 1]
      expect(source.listeners.report_completed).toHaveLength(1)

      store.setStatus('generating_report')
      source.emit('report_completed', { agreement_score: 0.82 })

      expect(store.status).toBe('running')
      expect(activity.entries.filter((entry) => entry.message === 'レポート生成完了')).toHaveLength(1)
      expect(activity.entries[0].detail).toBe('合意度: 82%')
    })
  })
})
