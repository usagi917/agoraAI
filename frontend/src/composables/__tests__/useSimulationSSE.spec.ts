import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

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
})
