import { useTheaterStore } from '../stores/theaterStore'
import { useActivityStore } from '../stores/activityStore'

/**
 * Theater SSEイベントハンドラー。
 * useSimulationSSE と組み合わせて使用する。
 * 5つのTheaterイベント(claim_made, stance_shifted, alliance_formed,
 * market_moved, decision_locked)を処理する。
 */
export function useTheaterSSE() {
  const theater = useTheaterStore()
  const activity = useActivityStore()

  function handleTheaterEvent(eventType: string, payload: Record<string, any>): boolean {
    switch (eventType) {
      case 'claim_made':
        theater.addClaim({
          agentId: payload.agent_id ?? '',
          claimText: payload.claim_text ?? '',
          stance: payload.stance ?? '',
          confidence: payload.confidence ?? 0,
        })
        activity.addEntry('agent', '💬', `${payload.agent_id ?? ''}: ${(payload.claim_text ?? '').slice(0, 60)}`, {
          track: 'agent',
          status: 'completed',
        })
        return true

      case 'stance_shifted':
        theater.addStanceShift({
          agentId: payload.agent_id ?? '',
          fromStance: payload.from_stance ?? '',
          toStance: payload.to_stance ?? '',
          reason: payload.reason ?? '',
        })
        activity.addEntry('event', '↔', `${payload.agent_id ?? ''} の立場が変化: ${payload.from_stance ?? ''} → ${payload.to_stance ?? ''}`, {
          track: 'agent',
          status: 'completed',
        })
        return true

      case 'alliance_formed': {
        const ids: string[] = payload.agent_ids ?? []
        theater.setAlliances([{
          agentIds: ids,
          stance: payload.stance ?? '',
          strength: payload.strength ?? 0,
        }])
        activity.addEntry('event', '🤝', `連合形成: ${ids.length}人が「${payload.stance ?? ''}」で一致`, {
          track: 'agent',
          status: 'completed',
        })
        return true
      }

      case 'market_moved':
        activity.addEntry('event', '📊', `予測変動: ${payload.old_prob ?? '?'}% → ${payload.new_prob ?? '?'}%`, {
          track: 'timeline',
          status: 'completed',
        })
        return true

      case 'decision_locked':
        theater.setDecision({
          decisionText: payload.decision_text ?? '',
          confidence: payload.confidence ?? 0,
          dissentCount: payload.dissent_count ?? 0,
        })
        activity.addEntry('phase', '🔒', `結論確定: ${(payload.decision_text ?? '').slice(0, 80)}`, {
          track: 'timeline',
          status: 'completed',
        })
        return true

      default:
        return false
    }
  }

  return { handleTheaterEvent }
}
