import { useTheaterStore } from '../stores/theaterStore'
import { useActivityStore } from '../stores/activityStore'

const NUMERIC_TO_STANCE: [number, string][] = [
  [1.0, '賛成'],
  [0.7, '条件付き賛成'],
  [0.5, '中立'],
  [0.3, '条件付き反対'],
  [0.0, '反対'],
]

function numericToStanceLabel(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value !== 'number') return '中立'
  let closest = NUMERIC_TO_STANCE[0]
  for (const entry of NUMERIC_TO_STANCE) {
    if (Math.abs(value - entry[0]) < Math.abs(value - closest[0])) {
      closest = entry
    }
  }
  return closest[1]
}

function toAgentLabel(agentId: unknown): string {
  if (agentId == null) return ''
  return String(agentId)
}

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
      case 'claim_made': {
        const label = toAgentLabel(payload.agent_id)
        theater.addClaim({
          agentId: label,
          claimText: payload.claim_text ?? '',
          stance: typeof payload.stance === 'string' ? payload.stance : numericToStanceLabel(payload.stance),
          confidence: payload.confidence ?? 0,
        })
        activity.addEntry('agent', '💬', `${label}: ${(payload.claim_text ?? '').slice(0, 60)}`, {
          track: 'agent',
          status: 'completed',
        })
        return true
      }

      case 'stance_shifted': {
        const label = toAgentLabel(payload.agent_id)
        const fromLabel = numericToStanceLabel(payload.from_stance)
        const toLabel = numericToStanceLabel(payload.to_stance)
        theater.addStanceShift({
          agentId: label,
          fromStance: fromLabel,
          toStance: toLabel,
          reason: payload.reason ?? '',
        })
        activity.addEntry('event', '↔', `${label} の立場が変化: ${fromLabel} → ${toLabel}`, {
          track: 'agent',
          status: 'completed',
        })
        return true
      }

      case 'alliance_formed': {
        const ids: string[] = (payload.agent_ids ?? []).map(toAgentLabel)
        const stanceLabel = numericToStanceLabel(payload.stance)
        theater.addAlliance({
          agentIds: ids,
          stance: stanceLabel,
          strength: payload.strength ?? 0,
        })
        activity.addEntry('event', '🤝', `連合形成: ${ids.length}人が「${stanceLabel}」で一致`, {
          track: 'agent',
          status: 'completed',
        })
        return true
      }

      case 'market_moved':
        activity.addEntry('event', '📊', `予測変動: ${Math.round((payload.old_prob ?? 0) * 100)}% → ${Math.round((payload.new_prob ?? 0) * 100)}%`, {
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
