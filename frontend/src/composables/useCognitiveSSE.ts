import { useCognitiveStore, type AgentBDIState, type MemoryEntry, type ReflectionEntry, type ToMRelation } from '../stores/cognitiveStore'
import { useEvaluationStore, type EvaluationRound } from '../stores/evaluationStore'

/**
 * 認知シミュレーション用SSEイベントハンドラー。
 * useSimulationSSE と組み合わせて使用する。
 */
export function useCognitiveSSE() {
  const cognitiveStore = useCognitiveStore()
  const evaluationStore = useEvaluationStore()

  function handleCognitiveEvent(eventType: string, payload: Record<string, any>) {
    switch (eventType) {
      case 'graphrag_started':
        break

      case 'graphrag_completed':
        break

      case 'cognitive_agents_initialized':
        cognitiveStore.setCognitiveMode('advanced')
        break

      case 'cognitive_cycles_completed': {
        // 個別エージェントの認知サイクル完了
        break
      }

      case 'agent_state_updated': {
        const state: AgentBDIState = {
          agentId: payload.agent_id,
          agentName: payload.agent_name || '',
          round: payload.round || 0,
          beliefs: payload.beliefs || [],
          desires: payload.desires || [],
          intentions: payload.intentions || [],
          actionTaken: payload.action_taken || '',
          reasoningChain: payload.reasoning_chain || '',
          trustMap: payload.trust_map || {},
          mentalModels: payload.mental_models || {},
        }
        cognitiveStore.updateAgentState(state)
        break
      }

      case 'memory_recorded': {
        const entry: MemoryEntry = {
          id: payload.id || '',
          agentId: payload.agent_id || '',
          memoryType: payload.memory_type || 'episodic',
          content: payload.content || '',
          importance: payload.importance || 0.5,
          round: payload.round || 0,
          isReflection: payload.is_reflection || false,
          reflectionLevel: payload.reflection_level || 0,
        }
        cognitiveStore.addMemoryEntry(entry)
        break
      }

      case 'reflection_generated': {
        const reflections = payload.reflections || []
        for (const r of reflections) {
          const entry: ReflectionEntry = {
            insight: r.insight || '',
            importance: r.importance || 0.5,
            level: r.reflection_level || 1,
            sourceIds: r.source_ids || [],
            round: payload.round || 0,
          }
          cognitiveStore.addReflection(entry)
        }
        break
      }

      case 'tom_updated': {
        const relations: ToMRelation[] = (payload.relations || []).map((r: any) => ({
          observer: r.observer || '',
          target: r.target || '',
          inferredGoals: r.inferred_goals || [],
          predictedAction: r.predicted_action || '',
          trustLevel: r.trust_level || 0.5,
          confidence: r.confidence || 0.5,
        }))
        cognitiveStore.updateToMRelations(relations)
        break
      }

      case 'social_network_updated':
        cognitiveStore.updateSocialNetwork(payload.network || { nodes: [], edges: [] })
        if (payload.coalitions) {
          cognitiveStore.updateCoalitions(payload.coalitions)
        }
        break

      case 'evaluation_completed': {
        const evaluation: EvaluationRound = {
          round: payload.round || 0,
          goalCompletion: payload.goal_completion || 0,
          relationshipMaintenance: payload.relationship_maintenance || 0,
          informationManagement: payload.information_management || 0,
          socialNormAdherence: payload.social_norm_adherence || 0,
          behavioralConsistency: payload.behavioral_consistency || 0,
          causalPlausibility: payload.causal_plausibility || 0,
          emergentComplexity: payload.emergent_complexity || 0,
          overallScore: payload.overall_score || 0,
        }
        evaluationStore.addRound(evaluation)
        break
      }
    }
  }

  return { handleCognitiveEvent }
}
