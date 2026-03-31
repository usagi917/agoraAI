import { useCognitiveStore, type AgentBDIState, type MemoryEntry, type ReflectionEntry, type ToMRelation } from '../stores/cognitiveStore'
import { useEvaluationStore, type EvaluationRound } from '../stores/evaluationStore'
import { useAgentVisualizationStore } from '../stores/agentVisualizationStore'

/**
 * 認知シミュレーション用SSEイベントハンドラー。
 * useSimulationSSE と組み合わせて使用する。
 */
export function useCognitiveSSE() {
  const cognitiveStore = useCognitiveStore()
  const evaluationStore = useEvaluationStore()
  const vizStore = useAgentVisualizationStore()

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

      case 'agent_thinking_started':
        vizStore.setThinkingAgent(payload.agent_id || payload.agent_name || '')
        break

      case 'agent_thinking_completed':
        vizStore.clearThinkingAgent(payload.agent_id || payload.agent_name || '')
        if (payload.status === 'success') {
          vizStore.addRecentThought({
            agentId: payload.agent_id || payload.agent_name || '',
            agentName: payload.agent_name || '',
            reasoningChain: payload.reasoning_chain || '',
            chosenAction: payload.chosen_action || '',
            timestamp: Date.now(),
          })
          vizStore.setAgentStatus(payload.agent_id || payload.agent_name || '', 'executing')
        }
        break

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
        vizStore.setAgentStatus(payload.agent_id, 'idle')
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

      case 'conversation_started':
        if (payload.initiator_id) {
          const participants = payload.participants || []
          const targetId = participants.find((p: string) => p !== payload.initiator_id) || ''
          vizStore.addCommunicationFlow({
            sourceId: payload.initiator_id,
            targetId,
            messageType: 'conversation',
            content: payload.topic || 'conversation started',
            timestamp: Date.now(),
          })
        }
        break

      case 'conversation_turn_advanced':
      case 'conversation_concluded':
        if (payload.initiator_id && payload.channel_id) {
          vizStore.addCommunicationFlow({
            sourceId: payload.initiator_id,
            targetId: '',
            messageType: 'conversation',
            content: payload.topic || eventType,
            timestamp: Date.now(),
          })
        }
        break

      case 'debate_result':
        if (payload.winner_agent_id) {
          vizStore.setAgentStatus(payload.winner_agent_id, 'idle')
        }
        for (const arg of payload.arguments || []) {
          if (arg.agent_id) {
            vizStore.setAgentStatus(arg.agent_id, 'idle')
            vizStore.addCommunicationFlow({
              sourceId: arg.agent_id,
              targetId: payload.winner_agent_id || '',
              messageType: 'debate',
              content: arg.claim || arg.type || 'debate argument',
              timestamp: Date.now(),
            })
          }
        }
        break
    }
  }

  return { handleCognitiveEvent }
}
