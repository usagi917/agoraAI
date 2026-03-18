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

  const averageScores = computed(() => {
    if (rounds.value.length === 0) return null

    const keys: (keyof Omit<EvaluationRound, 'round'>)[] = [
      'goalCompletion',
      'relationshipMaintenance',
      'informationManagement',
      'socialNormAdherence',
      'behavioralConsistency',
      'causalPlausibility',
      'emergentComplexity',
      'overallScore',
    ]

    const avg: Record<string, number> = {}
    for (const key of keys) {
      avg[key] =
        rounds.value.reduce((sum, r) => sum + (r[key] as number), 0) /
        rounds.value.length
    }
    return avg
  })

  // レーダーチャート用データ
  const radarData = computed(() => {
    if (!latestScore.value) return null
    return {
      labels: [
        '目標達成',
        '関係維持',
        '情報管理',
        '社会規範',
        '行動一貫性',
        '因果妥当性',
        '創発複雑さ',
      ],
      values: [
        latestScore.value.goalCompletion,
        latestScore.value.relationshipMaintenance,
        latestScore.value.informationManagement,
        latestScore.value.socialNormAdherence,
        latestScore.value.behavioralConsistency,
        latestScore.value.causalPlausibility,
        latestScore.value.emergentComplexity,
      ],
    }
  })

  function addRound(evaluation: EvaluationRound) {
    rounds.value.push(evaluation)
  }

  function setRounds(evaluations: EvaluationRound[]) {
    rounds.value = evaluations
  }

  return {
    rounds,
    latestScore,
    averageScores,
    radarData,
    addRound,
    setRounds,
  }
})
