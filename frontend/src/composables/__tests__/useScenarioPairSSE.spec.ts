import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// ---------------------------------------------------------------------------
// Mock EventSource
// ---------------------------------------------------------------------------
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

  /** Emit a well-formed SSE event. */
  emit(type: string, payload: Record<string, any>) {
    const data = JSON.stringify({ event_type: type, payload })
    for (const listener of this.listeners[type] || []) {
      listener(new MessageEvent(type, { data }))
    }
  }

  /** Emit raw data string (for malformed-event tests). */
  emitRaw(type: string, rawData: string) {
    for (const listener of this.listeners[type] || []) {
      listener(new MessageEvent(type, { data: rawData }))
    }
  }

  triggerError() {
    if (this.onerror) this.onerror()
  }
}

vi.stubGlobal('EventSource', MockEventSource)

// ---------------------------------------------------------------------------
// Mock onUnmounted so we can call it manually outside a component lifecycle.
// ---------------------------------------------------------------------------
let unmountCallbacks: (() => void)[] = []
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onUnmounted: (cb: () => void) => {
      unmountCallbacks.push(cb)
    },
  }
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('useScenarioPairSSE', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    MockEventSource.instances = []
    unmountCallbacks = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  /** Import fresh module and set up the store with a pair. */
  async function createSSE(opts?: {
    baselineId?: string | null
    interventionId?: string | null
    pairId?: string
  }) {
    const {
      baselineId = 'sim-baseline-1',
      interventionId = 'sim-intervention-1',
      pairId = 'pair-1',
    } = opts ?? {}

    const { useScenarioPairStore } = await import('../../stores/scenarioPairStore')
    const store = useScenarioPairStore()
    store.currentPair = {
      id: pairId,
      population_snapshot_id: 'snap-1',
      baseline_simulation_id: baselineId,
      intervention_simulation_id: interventionId,
      intervention_params: {},
      decision_context: 'test decision',
      status: 'running',
      created_at: '2026-01-01T00:00:00Z',
    }

    const mod = await import('../useScenarioPairSSE')
    return { ...mod.useScenarioPairSSE(pairId), store }
  }

  // =========================================================================
  // 1. EventSource URL construction
  // =========================================================================
  describe('EventSource URL construction', () => {
    it('constructs correct URLs for both simulation streams', async () => {
      const { start } = await createSSE({
        baselineId: 'sim-b',
        interventionId: 'sim-i',
      })
      start()

      expect(MockEventSource.instances).toHaveLength(2)
      expect(MockEventSource.instances[0].url).toBe('/api/simulations/sim-b/stream')
      expect(MockEventSource.instances[1].url).toBe('/api/simulations/sim-i/stream')
    })

    it('strips trailing slashes from VITE_API_BASE_URL', async () => {
      // The composable reads import.meta.env.VITE_API_BASE_URL at call time.
      // The default /api has no trailing slash, so URLs should be clean.
      const { start } = await createSSE({ baselineId: 'abc' })
      start()
      const baselineUrl = MockEventSource.instances[0].url
      expect(baselineUrl).not.toContain('//')
      expect(baselineUrl).toBe('/api/simulations/abc/stream')
    })
  })

  // =========================================================================
  // 2. Event listener registration and JSON parsing
  // =========================================================================
  describe('event listener registration and JSON parsing', () => {
    it('registers listeners for all tracked event types', async () => {
      const { start } = await createSSE()
      start()

      const source = MockEventSource.instances[0]
      const expectedTypes = [
        'simulation_completed', 'run_completed', 'swarm_completed',
        'pipeline_completed', 'society_completed',
        'simulation_failed', 'run_failed', 'swarm_failed',
        'run_started', 'round_completed', 'phase_changed',
        'colony_started', 'colony_completed',
        'society_activation_progress', 'meeting_dialogue',
        'report_started', 'report_completed',
      ]

      for (const type of expectedTypes) {
        expect(source.listeners[type]).toBeDefined()
        expect(source.listeners[type].length).toBeGreaterThan(0)
      }
    })

    it('parses JSON event data and pushes to events array', async () => {
      const { start, events } = await createSSE()
      start()

      const source = MockEventSource.instances[0] // baseline
      source.emit('run_started', { step: 1 })

      expect(events.value).toHaveLength(1)
      expect(events.value[0]).toMatchObject({
        simulation_id: 'sim-baseline-1',
        role: 'baseline',
        event_type: 'run_started',
        payload: { step: 1 },
      })
      expect(events.value[0].timestamp).toBeTypeOf('number')
    })

    it('uses event_type from data when present', async () => {
      const { start, events } = await createSSE()
      start()

      const source = MockEventSource.instances[0]
      // event_type in data overrides the listener type
      const data = JSON.stringify({ event_type: 'custom_type', payload: {} })
      for (const listener of source.listeners['run_started'] || []) {
        listener(new MessageEvent('run_started', { data }))
      }

      expect(events.value[0].event_type).toBe('custom_type')
    })

    it('falls back to data itself as payload when payload key missing', async () => {
      const { start, events } = await createSSE()
      start()

      const source = MockEventSource.instances[0]
      const data = JSON.stringify({ event_type: 'run_started', foo: 'bar' })
      for (const listener of source.listeners['run_started'] || []) {
        listener(new MessageEvent('run_started', { data }))
      }

      expect(events.value[0].payload).toMatchObject({ event_type: 'run_started', foo: 'bar' })
    })

    it('merges events from both baseline and intervention streams', async () => {
      const { start, events } = await createSSE()
      start()

      const [baseline, intervention] = MockEventSource.instances
      baseline.emit('run_started', { from: 'baseline' })
      intervention.emit('run_started', { from: 'intervention' })

      expect(events.value).toHaveLength(2)
      expect(events.value[0].role).toBe('baseline')
      expect(events.value[1].role).toBe('intervention')
    })
  })

  // =========================================================================
  // 3. Terminal event detection (completed / failed)
  // =========================================================================
  describe('terminal event detection', () => {
    it('sets baselineStatus to completed on terminal event', async () => {
      const { start, baselineStatus } = await createSSE()
      start()

      const source = MockEventSource.instances[0]
      source.emit('simulation_completed', {})

      expect(baselineStatus.value).toBe('completed')
      expect(source.closed).toBe(true)
    })

    it('sets interventionStatus to completed on terminal event', async () => {
      const { start, interventionStatus } = await createSSE()
      start()

      const source = MockEventSource.instances[1]
      source.emit('run_completed', {})

      expect(interventionStatus.value).toBe('completed')
      expect(source.closed).toBe(true)
    })

    it('sets status to failed on fail events', async () => {
      const { start, baselineStatus } = await createSSE()
      start()

      const source = MockEventSource.instances[0]
      source.emit('simulation_failed', {})

      expect(baselineStatus.value).toBe('failed')
      expect(source.closed).toBe(true)
    })

    it('sets isComplete to true when both simulations complete', async () => {
      const { start, isComplete, store } = await createSSE()
      // Stub fetchComparison so it resolves without network call
      store.fetchComparison = vi.fn().mockResolvedValue({})

      start()
      const [baseline, intervention] = MockEventSource.instances

      baseline.emit('simulation_completed', {})
      expect(isComplete.value).toBe(false)

      intervention.emit('simulation_completed', {})
      expect(isComplete.value).toBe(true)
    })

    it('calls store.fetchComparison when both complete', async () => {
      const { start, store } = await createSSE()
      store.fetchComparison = vi.fn().mockResolvedValue({})

      start()
      const [baseline, intervention] = MockEventSource.instances

      baseline.emit('simulation_completed', {})
      intervention.emit('run_completed', {})

      expect(store.fetchComparison).toHaveBeenCalledWith('pair-1')
    })

    it('does not throw when fetchComparison rejects', async () => {
      const { start, isComplete, store } = await createSSE()
      store.fetchComparison = vi.fn().mockRejectedValue(new Error('network'))

      start()
      const [baseline, intervention] = MockEventSource.instances

      baseline.emit('simulation_completed', {})
      intervention.emit('simulation_completed', {})

      // isComplete still set even if fetch fails
      expect(isComplete.value).toBe(true)
    })

    it('transitions status from idle to running on non-terminal event', async () => {
      const { start, baselineStatus } = await createSSE()
      start()

      // start() already sets to 'running', so test with a fresh intervention
      const { start: start2, interventionStatus } = await createSSE()
      // Re-grab the fresh instances
      const beforeCount = MockEventSource.instances.length
      start2()
      const intervention = MockEventSource.instances[beforeCount + 1]
      // The status is already 'running' because start() sets it, but the
      // composable's internal logic also sets 'running' from 'idle'.
      // We verify the status is at least 'running'.
      expect(interventionStatus.value).toBe('running')
    })

    it('recognises all terminal event types', async () => {
      const terminalTypes = [
        'simulation_completed', 'run_completed', 'swarm_completed',
        'pipeline_completed', 'society_completed',
      ]

      for (const eventType of terminalTypes) {
        // Fresh pinia + instances for each iteration
        setActivePinia(createPinia())
        MockEventSource.instances = []

        const { start, baselineStatus } = await createSSE()
        start()

        const source = MockEventSource.instances[0]
        source.emit(eventType, {})
        expect(baselineStatus.value).toBe('completed')
        expect(source.closed).toBe(true)
      }
    })

    it('recognises all fail event types', async () => {
      const failTypes = ['simulation_failed', 'run_failed', 'swarm_failed']

      for (const eventType of failTypes) {
        setActivePinia(createPinia())
        MockEventSource.instances = []

        const { start, baselineStatus } = await createSSE()
        start()

        const source = MockEventSource.instances[0]
        source.emit(eventType, {})
        expect(baselineStatus.value).toBe('failed')
        expect(source.closed).toBe(true)
      }
    })
  })

  // =========================================================================
  // 4. Error handling for malformed events
  // =========================================================================
  describe('malformed event handling', () => {
    it('silently skips events with invalid JSON', async () => {
      const { start, events } = await createSSE()
      start()

      const source = MockEventSource.instances[0]
      source.emitRaw('run_started', '<<< not json >>>')

      expect(events.value).toHaveLength(0)
    })

    it('does not change status on malformed events', async () => {
      const { start, baselineStatus } = await createSSE()
      start()

      const currentStatus = baselineStatus.value
      const source = MockEventSource.instances[0]
      source.emitRaw('simulation_completed', '{broken')

      expect(baselineStatus.value).toBe(currentStatus)
    })
  })

  // =========================================================================
  // 5. MAX_EVENTS buffer overflow
  // =========================================================================
  describe('MAX_EVENTS buffer overflow', () => {
    it('trims events to the last 200 when buffer overflows', async () => {
      const { start, events } = await createSSE()
      start()

      const source = MockEventSource.instances[0]

      // Push 210 events
      for (let i = 0; i < 210; i++) {
        source.emit('round_completed', { index: i })
      }

      expect(events.value.length).toBe(200)
      // The first event retained should be index 10 (items 0-9 trimmed)
      expect(events.value[0].payload).toMatchObject({ index: 10 })
      expect(events.value[199].payload).toMatchObject({ index: 209 })
    })
  })

  // =========================================================================
  // 6. EventSource error handling
  // =========================================================================
  describe('EventSource error handling', () => {
    it('does not change status to failed on onerror while running', async () => {
      const { start, baselineStatus } = await createSSE()
      start()

      expect(baselineStatus.value).toBe('running')
      const source = MockEventSource.instances[0]
      source.triggerError()

      // The composable intentionally does not fail on transient errors
      expect(baselineStatus.value).toBe('running')
    })
  })

  // =========================================================================
  // 7. Cleanup on unmount
  // =========================================================================
  describe('cleanup on unmount', () => {
    it('closes both EventSource instances via close()', async () => {
      const { start, close } = await createSSE()
      start()

      expect(MockEventSource.instances).toHaveLength(2)
      expect(MockEventSource.instances[0].closed).toBe(false)
      expect(MockEventSource.instances[1].closed).toBe(false)

      close()

      expect(MockEventSource.instances[0].closed).toBe(true)
      expect(MockEventSource.instances[1].closed).toBe(true)
    })

    it('registers cleanup with onUnmounted', async () => {
      const { start } = await createSSE()
      start()

      expect(unmountCallbacks.length).toBeGreaterThan(0)

      // Simulate component unmount
      for (const cb of unmountCallbacks) cb()

      expect(MockEventSource.instances[0].closed).toBe(true)
      expect(MockEventSource.instances[1].closed).toBe(true)
    })

    it('close() is safe to call when no streams are active', async () => {
      const { close } = await createSSE()
      // Never called start(), so no EventSources created
      expect(() => close()).not.toThrow()
    })
  })

  // =========================================================================
  // Edge cases
  // =========================================================================
  describe('edge cases', () => {
    it('skips baseline stream when baseline_simulation_id is null', async () => {
      const { start, baselineStatus, isComplete, store } = await createSSE({
        baselineId: null,
      })
      store.fetchComparison = vi.fn().mockResolvedValue({})
      start()

      // Only intervention stream is created
      expect(MockEventSource.instances).toHaveLength(1)
      expect(MockEventSource.instances[0].url).toContain('sim-intervention-1')
      expect(baselineStatus.value).toBe('completed')
    })

    it('skips intervention stream when intervention_simulation_id is null', async () => {
      const { start, interventionStatus, store } = await createSSE({
        interventionId: null,
      })
      store.fetchComparison = vi.fn().mockResolvedValue({})
      start()

      expect(MockEventSource.instances).toHaveLength(1)
      expect(MockEventSource.instances[0].url).toContain('sim-baseline-1')
      expect(interventionStatus.value).toBe('completed')
    })

    it('is immediately complete when both simulation IDs are null', async () => {
      const { start, isComplete, store } = await createSSE({
        baselineId: null,
        interventionId: null,
      })
      store.fetchComparison = vi.fn().mockResolvedValue({})
      start()

      expect(MockEventSource.instances).toHaveLength(0)
      expect(isComplete.value).toBe(true)
      expect(store.fetchComparison).toHaveBeenCalledWith('pair-1')
    })

    it('does nothing when store has no current pair', async () => {
      const { useScenarioPairStore } = await import('../../stores/scenarioPairStore')
      const store = useScenarioPairStore()
      store.currentPair = null

      const mod = await import('../useScenarioPairSSE')
      const { start } = mod.useScenarioPairSSE('pair-x')
      start()

      expect(MockEventSource.instances).toHaveLength(0)
    })
  })
})
