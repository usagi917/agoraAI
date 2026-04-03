import { ref, onUnmounted } from 'vue'
import { useScenarioPairStore } from '../stores/scenarioPairStore'

export interface ScenarioPairSSEEvent {
  simulation_id: string
  role: 'baseline' | 'intervention'
  event_type: string
  payload: Record<string, unknown>
  timestamp: number
}

function getSimulationStreamUrl(simulationId: string) {
  const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')
  return `${base}/simulations/${simulationId}/stream`
}

/**
 * Connects to SSE streams for both simulations in a scenario pair
 * and merges events into a single reactive stream.
 */
export function useScenarioPairSSE(pairId: string) {
  const store = useScenarioPairStore()
  const events = ref<ScenarioPairSSEEvent[]>([])
  const baselineStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
  const interventionStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
  const isComplete = ref(false)

  const MAX_EVENTS = 200

  let baselineSource: EventSource | null = null
  let interventionSource: EventSource | null = null

  function addEvent(
    simulationId: string,
    role: 'baseline' | 'intervention',
    eventType: string,
    payload: Record<string, unknown>,
  ) {
    events.value.push({
      simulation_id: simulationId,
      role,
      event_type: eventType,
      payload,
      timestamp: Date.now(),
    })
    if (events.value.length > MAX_EVENTS) {
      events.value = events.value.slice(-MAX_EVENTS)
    }
  }

  function checkCompletion() {
    if (baselineStatus.value === 'completed' && interventionStatus.value === 'completed') {
      isComplete.value = true
      store.fetchComparison(pairId).catch(() => {
        // comparison fetch may fail silently; user can retry
      })
    }
  }

  function connectStream(
    simulationId: string,
    role: 'baseline' | 'intervention',
  ): EventSource {
    const url = getSimulationStreamUrl(simulationId)
    const source = new EventSource(url)

    const statusRef = role === 'baseline' ? baselineStatus : interventionStatus

    const terminalEvents = [
      'simulation_completed', 'run_completed', 'swarm_completed',
      'pipeline_completed', 'society_completed',
    ]
    const failEvents = [
      'simulation_failed', 'run_failed', 'swarm_failed',
    ]
    const trackedEvents = [
      ...terminalEvents,
      ...failEvents,
      'run_started', 'round_completed', 'phase_changed',
      'colony_started', 'colony_completed',
      'society_activation_progress', 'meeting_dialogue',
      'report_started', 'report_completed',
    ]

    for (const type of trackedEvents) {
      source.addEventListener(type, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          const eventType = data.event_type || type
          addEvent(simulationId, role, eventType, data.payload || data)

          if (terminalEvents.includes(eventType)) {
            statusRef.value = 'completed'
            source.close()
            checkCompletion()
          } else if (failEvents.includes(eventType)) {
            statusRef.value = 'failed'
            source.close()
            checkCompletion()
          } else if (statusRef.value === 'idle') {
            statusRef.value = 'running'
          }
        } catch {
          // skip malformed events
        }
      })
    }

    source.onerror = () => {
      if (statusRef.value === 'running') {
        // Don't set to failed on transient errors; EventSource auto-reconnects
      }
    }

    return source
  }

  function start() {
    const pair = store.currentPair
    if (!pair) return

    if (pair.baseline_simulation_id) {
      baselineStatus.value = 'running'
      baselineSource = connectStream(pair.baseline_simulation_id, 'baseline')
    } else {
      baselineStatus.value = 'completed'
    }

    if (pair.intervention_simulation_id) {
      interventionStatus.value = 'running'
      interventionSource = connectStream(pair.intervention_simulation_id, 'intervention')
    } else {
      interventionStatus.value = 'completed'
    }

    checkCompletion()
  }

  function close() {
    baselineSource?.close()
    baselineSource = null
    interventionSource?.close()
    interventionSource = null
  }

  onUnmounted(close)

  return {
    events,
    baselineStatus,
    interventionStatus,
    isComplete,
    start,
    close,
  }
}
