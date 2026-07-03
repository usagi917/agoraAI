import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  createSimulation,
  getValidationReport,
  getValidationTopics,
  type ValidationReportResponse,
  type ValidationTopic,
} from '../api/client'

export const useValidationStore = defineStore('validation', () => {
  const topics = ref<ValidationTopic[]>([])
  const selectedSurveyId = ref<string>('')
  const runningSimulationId = ref<string | null>(null)
  const report = ref<ValidationReportResponse | null>(null)
  const loadingTopics = ref(false)
  const starting = ref(false)
  const loadingReport = ref(false)
  const error = ref('')

  const selectedTopic = computed(() =>
    topics.value.find((topic) => topic.survey_id === selectedSurveyId.value) || null,
  )

  function resetRunState() {
    runningSimulationId.value = null
    report.value = null
    error.value = ''
  }

  async function loadTopics() {
    loadingTopics.value = true
    error.value = ''
    try {
      const payload = await getValidationTopics('economy')
      topics.value = payload.topics
      if (!selectedSurveyId.value && payload.topics.length > 0) {
        selectedSurveyId.value = payload.topics[0].survey_id
      }
    } catch (err: any) {
      error.value = err?.response?.data?.detail || err?.message || 'トピック取得に失敗しました'
    } finally {
      loadingTopics.value = false
    }
  }

  async function startValidation(seed = 42) {
    if (starting.value || !selectedTopic.value) return null
    starting.value = true
    error.value = ''
    report.value = null
    try {
      const topic = selectedTopic.value
      const sim = await createSimulation({
        mode: 'unified',
        promptText: topic.theme,
        evidenceMode: 'prefer',
        seed,
        diagnostic: {
          survey_id: topic.survey_id,
          anchor_blend: false,
          stop_after: 'society_pulse',
        },
      })
      runningSimulationId.value = sim.id
      return sim.id
    } catch (err: any) {
      error.value = err?.response?.data?.detail || err?.message || '検証を開始できませんでした'
      return null
    } finally {
      starting.value = false
    }
  }

  async function loadReport(simId: string, surveyId = selectedSurveyId.value) {
    loadingReport.value = true
    error.value = ''
    try {
      report.value = await getValidationReport(simId, surveyId || undefined)
      runningSimulationId.value = simId
    } catch (err: any) {
      error.value = err?.response?.data?.detail || err?.message || '検証レポートを取得できませんでした'
      throw err
    } finally {
      loadingReport.value = false
    }
  }

  return {
    topics,
    selectedSurveyId,
    selectedTopic,
    runningSimulationId,
    report,
    loadingTopics,
    starting,
    loadingReport,
    error,
    resetRunState,
    loadTopics,
    startValidation,
    loadReport,
  }
})
