import { onUnmounted } from 'vue'
import { useSimulationStore, type ColonyState } from '../stores/simulationStore'
import { useGraphStore } from '../stores/graphStore'
import { useActivityStore } from '../stores/activityStore'
import { useCognitiveSSE } from './useCognitiveSSE'

function getSimulationStreamUrl(simulationId: string) {
  const base = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')
  return `${base}/simulations/${simulationId}/stream`
}

export function useSimulationSSE(simulationId: string) {
  const store = useSimulationStore()
  const graphStore = useGraphStore()
  const activity = useActivityStore()
  const { handleCognitiveEvent } = useCognitiveSSE()
  let source: EventSource | null = null

  function start() {
    const e2eEvents = (window as Window & {
      __AGENT_AI_E2E_EVENTS__?: Array<{ eventType: string; payload: Record<string, any>; delayMs?: number }>
    }).__AGENT_AI_E2E_EVENTS__
    if (Array.isArray(e2eEvents) && e2eEvents.length > 0) {
      for (const event of e2eEvents) {
        window.setTimeout(() => {
          ;(window as Window & { __AGENT_AI_E2E_LAST_EVENT__?: string }).__AGENT_AI_E2E_LAST_EVENT__ = event.eventType
          handleEvent(event.eventType, event.payload)
        }, event.delayMs ?? 0)
      }
      return
    }

    const url = getSimulationStreamUrl(simulationId)
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
      'report_failed',
      'verification_started',
      'verification_completed',
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
      'report_completed',
      'swarm_completed',
      'swarm_failed',
      // PM Board モード
      'pm_board_started',
      'pm_analyzing',
      'pm_analyses_completed',
      'pm_synthesizing',
      'pm_board_completed',
      // パイプラインイベント
      'pipeline_stage_started',
      'pipeline_stage_completed',
      'pipeline_completed',
      // 統一イベント
      'simulation_completed',
      'simulation_failed',
      // Society モード イベント
      'society_started',
      'population_status',
      'society_selection_completed',
      'society_activation_started',
      'society_activation_progress',
      'society_activation_completed',
      'society_evaluation_completed',
      'society_completed',
      // Meeting Layer イベント
      'meeting_started',
      'meeting_round_completed',
      'meeting_completed',
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
      // === パイプライン イベント ===
      case 'pipeline_stage_started':
        store.setPipelineStage(payload.stage)
        store.setPhase(payload.stage)
        store.setStatus('running')
        activity.addEntry('phase', '▶', `パイプライン Stage: ${payload.stage} 開始`, {
          track: 'phase',
          status: 'running',
        })
        break

      case 'pipeline_stage_completed':
        store.setStageProgress({
          ...store.stageProgress,
          [payload.stage]: 'completed',
        })
        break

      case 'pipeline_completed':
        store.setStatus('completed')
        store.setPhase('completed')
        store.setPipelineStage('completed')
        store.setReportReady(true)
        store.setReportError('')
        activity.addEntry('phase', '✓', 'パイプライン完了', {
          track: 'phase',
          status: 'completed',
        })
        close()
        break

      // === Single モード ===
      case 'run_started':
        store.setStatus('running')
        store.setPhase('world_building')
        if (payload.total_rounds) {
          store.setRound(0, payload.total_rounds)
        }
        activity.addEntry('phase', '◈', `シミュレーション開始 (${payload.total_rounds || '?'} ラウンド)`, {
          track: 'phase',
          status: 'running',
        })
        break

      case 'world_initialized':
        store.setPhase('simulation')
        if (payload.graph_diff) {
          graphStore.applyDiff(payload.graph_diff)
        }
        activity.addEntry('event', '◇', '世界モデル構築完了', {
          detail: payload.graph_diff ? `${payload.graph_diff.added_nodes?.length || 0} nodes` : undefined,
          track: 'graph',
          status: 'completed',
        })
        break

      case 'agents_built':
        activity.addEntry('event', '⊕', `エージェント構築完了 (${payload.agent_count || '?'}体)`, {
          track: 'agent',
          status: 'completed',
        })
        break

      case 'round_completed': {
        const round = payload.round || 0
        if (!payload.colony_id) {
          store.setRound(round)
          activity.addEntry('event', '⟳', `Round ${round} 完了`, {
            detail: payload.summary || undefined,
            round,
            track: 'timeline',
            status: 'completed',
          })
          // エージェントアクションをログに追加（先頭5件）
          if (payload.events?.length) {
            for (const evt of payload.events.slice(0, 5)) {
              activity.addEntry('agent', '●', evt.description || evt.action || 'action', {
                agentName: evt.agent_name || evt.agent_id,
                round,
                track: 'agent',
                status: 'completed',
              })
            }
          }
        } else {
          store.updateColonyStatus(payload.colony_id, 'running', {
            currentRound: round,
          } as Partial<ColonyState>)
          activity.addEntry('event', '⟳', `Colony ${payload.colony_id.slice(0, 6)} Round ${round}`, {
            round,
            track: 'swarm',
            status: 'running',
          })
        }
        break
      }

      case 'graph_diff':
        graphStore.applyDiff(payload)
        activity.addEntry('info', '◎', `グラフ更新: +${payload.added_nodes?.length || 0} nodes, +${payload.added_edges?.length || 0} edges`, {
          track: 'graph',
          status: 'completed',
        })
        break

      case 'timeline_event':
        activity.addEntry('event', '◌', payload.title || payload.event_type || 'timeline', {
          detail: payload.description || undefined,
          round: payload.round,
          track: 'timeline',
          status: 'completed',
        })
        break

      case 'report_started':
        store.setStatus('generating_report')
        store.setPhase('report')
        store.setReportSections(payload.sections || [])
        store.setReportError('')
        activity.addEntry('phase', '▣', 'レポート生成開始', {
          detail: payload.sections ? `${payload.sections.length} セクション` : undefined,
          track: 'report',
          status: 'running',
        })
        break

      case 'report_section_done':
        store.completeReportSection(payload.index ?? payload.section)
        activity.addEntry('info', '▪', `セクション完了: ${payload.section || ''}`, {
          track: 'report',
          status: 'completed',
        })
        break

      case 'report_completed':
        store.setReportError('')
        store.setStatus('running')
        activity.addEntry('event', '▣', 'レポート生成完了', {
          track: 'report',
          status: 'completed',
        })
        break

      case 'report_failed':
        store.setStatus('running')
        store.setReportError(payload.error || 'レポート生成に失敗しました')
        activity.addEntry('error', '✗', 'レポート生成失敗', {
          detail: payload.error || undefined,
          track: 'report',
          status: 'failed',
        })
        break

      case 'verification_started':
        store.setPhase('verification')
        activity.addEntry('phase', '◌', `検証開始: ${payload.target || 'output'}`, {
          detail: payload.scope || undefined,
          track: 'report',
          status: 'running',
        })
        break

      case 'verification_completed':
        activity.addEntry(
          payload.status === 'passed' ? 'event' : 'error',
          payload.status === 'passed' ? '✓' : '✗',
          `検証完了: ${payload.target || 'output'}`,
          {
            detail: payload.status ? `${payload.status} / ${(Number(payload.score || 0) * 100).toFixed(0)}%` : undefined,
            track: 'report',
            status: payload.status === 'passed' ? 'completed' : 'failed',
          },
        )
        if (store.status === 'generating_report') {
          store.setPhase('report')
        }
        break

      case 'run_completed':
        // パイプラインモードでは run_completed は Stage 1 完了を意味する（全体完了ではない）
        if (!store.isPipelineMode) {
          store.setStatus('completed')
          store.setPhase('completed')
          close()
        }
        break

      case 'run_failed':
        store.setError(payload.error || '不明なエラー')
        activity.addEntry('error', '✗', `エラー: ${payload.error || '不明なエラー'}`)
        if (!store.isPipelineMode) {
          close()
        }
        break

      // === Swarm モード ===
      case 'swarm_started':
        if (!store.isPipelineMode) {
          store.setStatus('running')
        }
        store.setPhase('world_building')
        activity.addEntry('phase', '⬡', 'Swarm シミュレーション開始', {
          track: 'phase',
          status: 'running',
        })
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
        activity.addEntry('event', '⬡', `Colony ${payload.colony_id.slice(0, 6)} 開始`, {
          detail: payload.perspective || undefined,
          track: 'swarm',
          status: 'running',
        })
        break

      case 'colony_completed':
        store.updateColonyStatus(payload.colony_id, 'completed', {
          eventCount: payload.event_count || 0,
        } as Partial<ColonyState>)
        activity.addEntry('event', '⬡', `Colony ${payload.colony_id.slice(0, 6)} 完了`, {
          detail: `${payload.event_count || 0} events`,
          track: 'swarm',
          status: 'completed',
        })
        break

      case 'colonies_completed':
        store.setPhase('aggregation')
        break

      case 'aggregation_completed':
        store.setPhase('completed')
        break

      case 'swarm_completed':
        // パイプラインモードでは swarm_completed は Stage 2 完了を意味する
        if (!store.isPipelineMode) {
          store.setStatus('completed')
          store.setPhase('completed')
          close()
        }
        break

      case 'swarm_failed':
        store.setError(payload.error || '不明なエラー')
        if (!store.isPipelineMode) {
          close()
        }
        break

      // === PM Board モード ===
      case 'pm_board_started':
        if (!store.isPipelineMode) {
          store.setStatus('running')
        }
        store.setPhase('pm_analyzing')
        activity.addEntry('phase', '◉', 'PM Board 分析開始', {
          track: 'phase',
          status: 'running',
        })
        break

      case 'pm_analyzing':
        store.setPhase(`pm_analyzing_${payload.persona}`)
        activity.addEntry('agent', '◉', `${payload.persona} 分析中...`, {
          agentName: payload.persona,
          track: 'agent',
          status: 'running',
        })
        break

      case 'pm_analyses_completed':
        store.setPhase('pm_synthesizing')
        break

      case 'pm_synthesizing':
        store.setPhase('pm_synthesizing')
        break

      case 'pm_board_completed':
        if (!store.isPipelineMode) {
          store.setStatus('completed')
          store.setPhase('completed')
          close()
        }
        break

      // === Society モード ===
      case 'society_started':
        store.setStatus('running')
        store.setSocietyPhase('population')
        store.setPhase('society_population')
        activity.addEntry('phase', '▶', 'Society シミュレーション開始', {
          track: 'phase',
          status: 'running',
        })
        break

      case 'population_status':
        if (payload.status === 'ready') {
          store.setSocietyPhase('selection')
          activity.addEntry('event', '◇', `人口生成完了 (${payload.agent_count}人)`, {
            track: 'phase',
            status: 'completed',
          })
        }
        break

      case 'society_selection_completed':
        store.setSocietyPhase('activation')
        store.setPhase('society_activation')
        activity.addEntry('event', '◎', `${payload.selected_count}人を選抜`, {
          detail: `${payload.total_population}人から${payload.selected_count}人を選出`,
          track: 'agent',
          status: 'completed',
        })
        break

      case 'society_activation_started':
        store.setSocietyPhase('activation')
        activity.addEntry('phase', '⬡', `活性化開始 (${payload.agent_count}人)`, {
          track: 'phase',
          status: 'running',
        })
        break

      case 'society_activation_progress':
        store.setSocietyActivationProgress(payload.completed, payload.total)
        break

      case 'society_activation_completed':
        store.setSocietyPhase('evaluation')
        store.setPhase('society_evaluation')
        if (payload.aggregation?.stance_distribution) {
          store.setOpinionDistribution(payload.aggregation.stance_distribution)
        }
        activity.addEntry('event', '◎', '活性化完了', {
          detail: `平均信頼度: ${(payload.aggregation?.average_confidence * 100)?.toFixed(1)}%`,
          track: 'phase',
          status: 'completed',
        })
        break

      case 'society_evaluation_completed':
        store.setEvaluationMetrics(payload.metrics || {})
        activity.addEntry('event', '▣', '評価完了', {
          track: 'phase',
          status: 'completed',
        })
        break

      case 'meeting_started':
        store.setSocietyPhase('meeting')
        store.setPhase('society_meeting')
        activity.addEntry('phase', '◉', `Meeting 開始 (${payload.participant_count}人, ${payload.num_rounds}R)`, {
          track: 'phase',
          status: 'running',
        })
        break

      case 'meeting_round_completed':
        activity.addEntry('event', '◉', `Meeting Round ${payload.round}: ${payload.round_name}`, {
          detail: `${payload.argument_count}件の発言`,
          track: 'agent',
          status: 'completed',
        })
        break

      case 'meeting_completed':
        activity.addEntry('event', '◉', 'Meeting 完了', {
          track: 'phase',
          status: 'completed',
        })
        break

      case 'society_completed':
        store.setStatus('completed')
        store.setPhase('completed')
        store.setSocietyPhase('completed')
        store.setReportReady(true)
        if (payload.aggregation?.stance_distribution) {
          store.setOpinionDistribution(payload.aggregation.stance_distribution)
        }
        if (payload.evaluation) {
          store.setEvaluationMetrics(payload.evaluation)
        }
        activity.addEntry('phase', '✓', 'Society シミュレーション完了', {
          track: 'phase',
          status: 'completed',
        })
        close()
        break

      // === 統一イベント ===
      case 'simulation_completed':
        store.setStatus('completed')
        store.setPhase('completed')
        store.setReportReady(true)
        store.setReportError('')
        close()
        break

      case 'simulation_failed':
        store.setError(payload.error || '不明なエラー')
        activity.addEntry('error', '✗', `シミュレーション失敗: ${payload.error || '不明なエラー'}`)
        close()
        break

      // === 認知シミュレーション イベント ===
      default:
        // 認知関連イベントは専用ハンドラーに委譲
        handleCognitiveEvent(eventType, payload)
        if (eventType === 'graphrag_started') {
          store.setPhase('graphrag')
          activity.addEntry('phase', '◈', 'GraphRAG 構築開始', {
            track: 'graph',
            status: 'running',
          })
        } else if (eventType === 'graphrag_completed') {
          store.setPhase('world_building')
          activity.addEntry('event', '◈', 'GraphRAG 構築完了', {
            track: 'graph',
            status: 'completed',
          })
        } else if (eventType === 'agent_state_updated') {
          activity.addEntry('agent', '●', `${payload.agent_name || payload.agent_id} ${payload.action_taken || ''}`, {
            agentName: payload.agent_name || payload.agent_id,
            round: payload.round,
            track: 'agent',
            status: 'completed',
          })
        }
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
