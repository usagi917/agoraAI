import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface EvaluationRound {
  round: number
  goalCompletion: number
  relationshipMaintenance: number
  informationManagement: number
  socialNormAdherence: number
  behavioralConsistency: number
  causalPlausibility: number
  emergentComplexity: number
  overallScore: number
}

export const useEvaluationStore = defineStore('evaluation', () => {
  const rounds = ref<EvaluationRound[]>([])

  const latestScore = computed(() =>
    rounds.value.length > 0 ? rounds.value[rounds.value.length - 1] : null,
  )

  function addRound(evaluation: EvaluationRound) {
    rounds.value.push(evaluation)
  }

  function setRounds(evaluations: EvaluationRound[]) {
    rounds.value = evaluations
  }

  return {
    rounds,
    latestScore,
    addRound,
    setRounds,
  }
})
