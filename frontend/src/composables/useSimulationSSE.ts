import { onUnmounted } from 'vue'
import { useSimulationStore, type ColonyState } from '../stores/simulationStore'
import { useGraphStore } from '../stores/graphStore'
import { useCognitiveSSE } from './useCognitiveSSE'

export function useSimulationSSE(simulationId: string) {
  const store = useSimulationStore()
  const graphStore = useGraphStore()
  const { handleCognitiveEvent } = useCognitiveSSE()
  let source: EventSource | null = null

  function start() {
    const url = `/api/simulations/${simulationId}/stream`
    source = new EventSource(url)

    const eventTypes = [
      // Single モード
      'run_started',
      'world_initialized',
      'agents_built',
      'round_completed',
      'graph_diff',
      'timeline_event',
      'report_started',
      'report_section_done',
      'run_completed',
      'run_failed',
      // Swarm モード
      'swarm_started',
      'phase_changed',
      'colonies_created',
      'colony_started',
      'colony_completed',
      'colonies_completed',
      'aggregation_completed',
      'swarm_completed',
      'swarm_failed',
      // 統一イベント
      'simulation_completed',
      'simulation_failed',
      // 認知シミュレーション イベント
      'graphrag_started',
      'graphrag_completed',
      'cognitive_agents_initialized',
      'cognitive_cycles_completed',
      'agent_state_updated',
      'memory_recorded',
      'reflection_generated',
      'tom_updated',
      'social_network_updated',
      'evaluation_completed',
    ]

    for (const type of eventTypes) {
      source.addEventListener(type, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          handleEvent(data.event_type, data.payload)
        } catch (err) {
          console.error('Simulation SSE parse error:', err)
        }
      })
    }

    source.onerror = () => {
      if (store.status !== 'completed' && store.status !== 'failed') {
        store.setStatus('disconnected')
      }
    }
  }

  function handleEvent(eventType: string, payload: Record<string, any>) {
    switch (eventType) {
      // === Single モード ===
      case 'run_started':
        store.setStatus('running')
        store.setPhase('world_building')
        if (payload.total_rounds) {
          store.setRound(0, payload.total_rounds)
        }
        break

      case 'world_initialized':
        store.setPhase('simulation')
        if (payload.graph_diff) {
          graphStore.applyDiff(payload.graph_diff)
        }
        break

      case 'agents_built':
        break

      case 'round_completed':
        if (!payload.colony_id) {
          // Single モードのラウンド
          store.setRound(payload.round || 0)
        } else {
          // Swarm Colony のラウンド
          store.updateColonyStatus(payload.colony_id, 'running', {
            currentRound: payload.round || 0,
          } as Partial<ColonyState>)
        }
        break

      case 'graph_diff':
        graphStore.applyDiff(payload)
        break

      case 'timeline_event':
        break

      case 'report_started':
        store.setStatus('generating_report')
        store.setPhase('report')
        break

      case 'report_section_done':
        break

      case 'run_completed':
        store.setStatus('completed')
        store.setPhase('completed')
        close()
        break

      case 'run_failed':
        store.setError(payload.error || '不明なエラー')
        close()
        break

      // === Swarm モード ===
      case 'swarm_started':
        store.setStatus('running')
        store.setPhase('world_building')
        break

      case 'phase_changed':
        store.setPhase(payload.phase)
        break

      case 'colonies_created':
        if (payload.colonies) {
          const colonyStates: ColonyState[] = payload.colonies.map((c: any, i: number) => ({
            id: c.colony_id,
            colonyIndex: i,
            perspectiveId: c.perspective_id || '',
            perspectiveLabel: c.perspective || '',
            temperature: c.temperature,
            adversarial: c.adversarial,
            status: 'queued',
            currentRound: 0,
            totalRounds: 0,
            eventCount: 0,
          }))
          store.setColonies(colonyStates)
        }
        break

      case 'colony_started':
        store.updateColonyStatus(payload.colony_id, 'running')
        break

      case 'colony_completed':
        store.updateColonyStatus(payload.colony_id, 'completed', {
          eventCount: payload.event_count || 0,
        } as Partial<ColonyState>)
        break

      case 'colonies_completed':
        store.setPhase('aggregation')
        break

      case 'aggregation_completed':
        store.setPhase('completed')
        break

      case 'swarm_completed':
        store.setStatus('completed')
        store.setPhase('completed')
        close()
        break

      case 'swarm_failed':
        store.setError(payload.error || '不明なエラー')
        close()
        break

      // === 統一イベント ===
      case 'simulation_completed':
        store.setStatus('completed')
        store.setPhase('completed')
        close()
        break

      case 'simulation_failed':
        store.setError(payload.error || '不明なエラー')
        close()
        break

      // === 認知シミュレーション イベント ===
      default:
        // 認知関連イベントは専用ハンドラーに委譲
        handleCognitiveEvent(eventType, payload)
        break
    }
  }

  function close() {
    source?.close()
    source = null
  }

  onUnmounted(close)

  return { start, close }
}
