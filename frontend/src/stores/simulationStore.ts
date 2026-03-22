import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PipelineStage } from '../api/client'

export interface ColonyState {
  id: string
  colonyIndex: number
  perspectiveId: string
  perspectiveLabel: string
  temperature: number
  adversarial: boolean
  status: string
  currentRound: number
  totalRounds: number
  eventCount: number
}

export interface ReportSectionState {
  name: string
  done: boolean
}

export interface SimulationStoreSnapshot {
  simulationId: string | null
  mode: string
  status: string
  phase: string
  promptText: string
  pipelineStage: PipelineStage
  stageProgress: Record<string, string>
  currentRound: number
  totalRounds: number
  colonies: ColonyState[]
  reportReady: boolean
  reportSections: ReportSectionState[]
  reportError: string
}

export const useSimulationStore = defineStore('simulation', () => {
  // 基本状態
  const simulationId = ref<string | null>(null)
  const mode = ref<string>('pipeline')
  const status = ref<string>('idle')
  const phase = ref<string>('queued')
  const error = ref('')
  const promptText = ref('')

  // パイプライン状態
  const pipelineStage = ref<PipelineStage>('pending')
  const stageProgress = ref<Record<string, string>>({})

  // Single モード状態
  const currentRound = ref(0)
  const totalRounds = ref(0)

  // Swarm/Hybrid モード状態
  const colonies = ref<ColonyState[]>([])

  // Society モード状態
  const societyPhase = ref<string>('idle') // idle | population | selection | activation | evaluation | completed
  const opinionDistribution = ref<Record<string, number>>({})
  const evaluationMetrics = ref<Record<string, number>>({})
  const societyActivationProgress = ref<{ completed: number; total: number }>({ completed: 0, total: 0 })

  // 算出プロパティ
  const completedColonies = computed(() =>
    colonies.value.filter(c => c.status === 'completed').length,
  )

  const isPipelineMode = computed(() => mode.value === 'pipeline')
  const isSocietyMode = computed(() => mode.value === 'society' || mode.value === 'society_first')

  const progress = computed(() => {
    if (status.value === 'completed') return 1

    if (isPipelineMode.value) {
      // パイプラインモード: 3段階で均等配分
      const stageWeights: Record<PipelineStage, number> = {
        pending: 0,
        single: 0,
        swarm: 0.33,
        pm_board: 0.66,
        completed: 1,
      }
      const baseProgress = stageWeights[pipelineStage.value] || 0

      // 各段階内の進捗を加算
      if (pipelineStage.value === 'single') {
        if (totalRounds.value === 0) return 0.05
        return Math.min(0.33, currentRound.value / totalRounds.value * 0.3 + 0.02)
      }
      if (pipelineStage.value === 'swarm') {
        if (colonies.value.length === 0) return baseProgress + 0.02
        return baseProgress + completedColonies.value / colonies.value.length * 0.33
      }
      if (pipelineStage.value === 'pm_board') {
        return baseProgress + 0.15 // PM Board は段階内の進捗を細かく追えないため固定
      }
      return baseProgress
    }

    // 旧モード互換
    if (mode.value === 'single') {
      if (totalRounds.value === 0) return 0.05
      return Math.min(0.85, currentRound.value / totalRounds.value * 0.8 + 0.1)
    }

    // swarm/hybrid
    if (colonies.value.length === 0) return 0.05
    return completedColonies.value / colonies.value.length
  })

  // レポート準備完了フラグ
  const reportReady = ref(false)

  // レポートセクション進行状況 (WP6)
  const reportSections = ref<ReportSectionState[]>([])
  const reportError = ref('')

  const completedReportSections = computed(() =>
    reportSections.value.filter(s => s.done).length,
  )

  // アクション
  function init(id: string, simMode: string = 'pipeline', prompt: string = '') {
    simulationId.value = id
    mode.value = simMode
    promptText.value = prompt
    status.value = 'connecting'
    phase.value = 'queued'
    pipelineStage.value = 'pending'
    stageProgress.value = {}
    currentRound.value = 0
    totalRounds.value = 0
    colonies.value = []
    error.value = ''
    reportReady.value = false
    reportSections.value = []
    reportError.value = ''
    societyPhase.value = 'idle'
    opinionDistribution.value = {}
    evaluationMetrics.value = {}
    societyActivationProgress.value = { completed: 0, total: 0 }
  }

  function setReportReady(ready: boolean) {
    reportReady.value = ready
  }

  function setReportSections(sections: string[]) {
    reportSections.value = sections.map(name => ({ name, done: false }))
  }

  function setReportSectionsState(sections: ReportSectionState[]) {
    reportSections.value = sections.map((section) => ({ ...section }))
  }

  function completeReportSection(indexOrName: number | string) {
    if (typeof indexOrName === 'number') {
      if (reportSections.value[indexOrName]) {
        reportSections.value[indexOrName].done = true
      }
    } else {
      const sec = reportSections.value.find(s => s.name === indexOrName)
      if (sec) sec.done = true
    }
  }

  function setReportError(message: string) {
    reportError.value = message
  }

  function toSnapshot(): SimulationStoreSnapshot {
    return {
      simulationId: simulationId.value,
      mode: mode.value,
      status: status.value,
      phase: phase.value,
      promptText: promptText.value,
      pipelineStage: pipelineStage.value,
      stageProgress: { ...stageProgress.value },
      currentRound: currentRound.value,
      totalRounds: totalRounds.value,
      colonies: colonies.value.map((colony) => ({ ...colony })),
      reportReady: reportReady.value,
      reportSections: reportSections.value.map((section) => ({ ...section })),
      reportError: reportError.value,
    }
  }

  function restoreSnapshot(
    snapshot: Partial<SimulationStoreSnapshot>,
    options: {
      preserveStatus?: boolean
      preservePhase?: boolean
      preservePipelineStage?: boolean
    } = {},
  ) {
    simulationId.value = snapshot.simulationId ?? simulationId.value
    mode.value = snapshot.mode ?? mode.value
    promptText.value = snapshot.promptText ?? promptText.value
    stageProgress.value = snapshot.stageProgress ? { ...snapshot.stageProgress } : stageProgress.value
    currentRound.value = snapshot.currentRound ?? currentRound.value
    totalRounds.value = snapshot.totalRounds ?? totalRounds.value
    colonies.value = snapshot.colonies
      ? snapshot.colonies.map((colony) => ({ ...colony }))
      : colonies.value
    reportReady.value = snapshot.reportReady ?? reportReady.value
    reportSections.value = snapshot.reportSections
      ? snapshot.reportSections.map((section) => ({ ...section }))
      : reportSections.value
    reportError.value = snapshot.reportError ?? reportError.value

    if (!options.preserveStatus && snapshot.status) {
      status.value = snapshot.status
    }
    if (!options.preservePhase && snapshot.phase) {
      phase.value = snapshot.phase
    }
    if (!options.preservePipelineStage && snapshot.pipelineStage) {
      pipelineStage.value = snapshot.pipelineStage
    }
  }

  function setStatus(s: string) {
    status.value = s
  }

  function setPhase(p: string) {
    phase.value = p
  }

  function setError(msg: string) {
    error.value = msg
    status.value = 'failed'
  }

  function setRound(round: number, total?: number) {
    currentRound.value = round
    if (total !== undefined) totalRounds.value = total
  }

  function setPipelineStage(stage: PipelineStage) {
    pipelineStage.value = stage
  }

  function setStageProgress(progress: Record<string, string>) {
    stageProgress.value = progress
  }

  function setColonies(colonyList: ColonyState[]) {
    colonies.value = colonyList
  }

  function setSocietyPhase(p: string) {
    societyPhase.value = p
  }

  function setOpinionDistribution(dist: Record<string, number>) {
    opinionDistribution.value = dist
  }

  function setEvaluationMetrics(metrics: Record<string, number>) {
    evaluationMetrics.value = metrics
  }

  function setSocietyActivationProgress(completed: number, total: number) {
    societyActivationProgress.value = { completed, total }
  }

  function updateColonyStatus(colonyId: string, newStatus: string, extra?: Partial<ColonyState>) {
    const colony = colonies.value.find(c => c.id === colonyId)
    if (colony) {
      colony.status = newStatus
      if (extra) Object.assign(colony, extra)
    }
  }

  return {
    simulationId,
    mode,
    status,
    phase,
    error,
    promptText,
    pipelineStage,
    stageProgress,
    currentRound,
    totalRounds,
    colonies,
    completedColonies,
    isPipelineMode,
    isSocietyMode,
    progress,
    reportReady,
    reportSections,
    reportError,
    completedReportSections,
    init,
    setStatus,
    setPhase,
    setError,
    setRound,
    setPipelineStage,
    setStageProgress,
    setColonies,
    updateColonyStatus,
    societyPhase,
    opinionDistribution,
    evaluationMetrics,
    societyActivationProgress,
    setSocietyPhase,
    setOpinionDistribution,
    setEvaluationMetrics,
    setSocietyActivationProgress,
    setReportReady,
    setReportSections,
    setReportSectionsState,
    completeReportSection,
    setReportError,
    toSnapshot,
    restoreSnapshot,
  }
})
