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
  metaCycleIndex?: number
  metaMaxCycles?: number
  metaTargetScore?: number
  metaBestScore?: number
  metaStopReason?: string
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

  // Network Propagation 状態 (Swarm Intelligence)
  const propagationTimesteps = ref<Array<{
    timestep: number
    opinion_distribution: Record<string, number>
    entropy: number
    cluster_count: number
    max_delta: number
  }>>([])
  const propagationCompleted = ref(false)
  const propagationClusters = ref<Array<{ label: number; size: number; centroid: number[] }>>([])
  const echoChamberMetrics = ref<{ homophily_index: number; polarization_index: number }>({
    homophily_index: 0,
    polarization_index: 0,
  })

  // Unified モード状態
  const unifiedPhase = ref<'idle' | 'society_pulse' | 'council' | 'synthesis' | 'completed'>('idle')
  const unifiedPhaseIndex = ref(0)
  const unifiedPhaseTotal = ref(3)

  // Meta Simulation 状態
  const metaPhase = ref<string>('idle')
  const metaCycleIndex = ref(0)
  const metaMaxCycles = ref(0)
  const metaTargetScore = ref(0)
  const metaBestScore = ref(0)
  const metaStopReason = ref('')
  const metaSelectedIntervention = ref<Record<string, any> | null>(null)

  // 算出プロパティ
  const completedColonies = computed(() =>
    colonies.value.filter(c => c.status === 'completed').length,
  )

  const PRESET_MODES = new Set(['quick', 'standard', 'deep', 'research', 'baseline'])
  const isPresetMode = computed(() => PRESET_MODES.has(mode.value))
  const isPipelineMode = computed(() => mode.value === 'pipeline' || mode.value === 'deep')
  const isMetaMode = computed(() => mode.value === 'meta_simulation' || mode.value === 'research')
  const isUnifiedMode = computed(() => mode.value === 'unified' || mode.value === 'standard' || mode.value === 'quick')
  const isSocietyMode = computed(() =>
    mode.value === 'society' || mode.value === 'society_first' || mode.value === 'unified'
    || mode.value === 'standard' || mode.value === 'quick' || mode.value === 'deep' || mode.value === 'research',
  )

  const progress = computed(() => {
    if (status.value === 'completed') return 1

    // 新プリセットモード: unifiedPhase で進捗を追跡
    if (isPresetMode.value || isUnifiedMode.value) {
      const phaseWeights: Record<string, number> = {
        idle: 0,
        society_pulse: 0.1,
        council: 0.4,
        multi_perspective: 0.5,
        issue_mining: 0.3,
        pm_analysis: 0.7,
        intervention: 0.6,
        synthesis: 0.85,
        completed: 1.0,
      }
      return phaseWeights[unifiedPhase.value] ?? 0
    }

    if (isMetaMode.value) {
      const phaseWeight: Record<string, number> = {
        world_building: 0.05,
        society: 0.2,
        issue_mining: 0.35,
        issue_swarm: 0.55,
        pm_board: 0.75,
        scoring: 0.9,
        completed: 1,
      }
      const intraCycle = phaseWeight[metaPhase.value] ?? 0.1
      if (metaMaxCycles.value <= 0) return intraCycle
      const priorCycles = Math.max(metaCycleIndex.value - 1, 0) / metaMaxCycles.value
      const currentCycle = intraCycle / metaMaxCycles.value
      return Math.min(0.98, priorCycles + currentCycle)
    }

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
    propagationTimesteps.value = []
    propagationCompleted.value = false
    propagationClusters.value = []
    echoChamberMetrics.value = { homophily_index: 0, polarization_index: 0 }
    unifiedPhase.value = 'idle'
    unifiedPhaseIndex.value = 0
    unifiedPhaseTotal.value = 3
    metaPhase.value = 'idle'
    metaCycleIndex.value = 0
    metaMaxCycles.value = 0
    metaTargetScore.value = 0
    metaBestScore.value = 0
    metaStopReason.value = ''
    metaSelectedIntervention.value = null
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
      metaCycleIndex: metaCycleIndex.value,
      metaMaxCycles: metaMaxCycles.value,
      metaTargetScore: metaTargetScore.value,
      metaBestScore: metaBestScore.value,
      metaStopReason: metaStopReason.value,
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
    metaCycleIndex.value = snapshot.metaCycleIndex ?? metaCycleIndex.value
    metaMaxCycles.value = snapshot.metaMaxCycles ?? metaMaxCycles.value
    metaTargetScore.value = snapshot.metaTargetScore ?? metaTargetScore.value
    metaBestScore.value = snapshot.metaBestScore ?? metaBestScore.value
    metaStopReason.value = snapshot.metaStopReason ?? metaStopReason.value

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

  function addPropagationTimestep(ts: {
    timestep: number
    opinion_distribution: Record<string, number>
    entropy: number
    cluster_count: number
    max_delta: number
  }) {
    propagationTimesteps.value.push(ts)
  }

  function setPropagationCompleted(data: {
    converged: boolean
    cluster_count: number
    clusters?: Array<{ label: number; size: number; centroid: number[] }>
    echo_chamber?: { homophily_index: number; polarization_index: number }
    opinionDistribution?: Record<string, number>
  }) {
    propagationCompleted.value = true
    if (data.clusters) propagationClusters.value = data.clusters
    if (data.echo_chamber) echoChamberMetrics.value = data.echo_chamber
    if (data.opinionDistribution) opinionDistribution.value = data.opinionDistribution
  }

  function setEvaluationMetrics(metrics: Record<string, number>) {
    evaluationMetrics.value = metrics
  }

  function setSocietyActivationProgress(completed: number, total: number) {
    societyActivationProgress.value = { completed, total }
  }

  function setUnifiedPhase(p: 'idle' | 'society_pulse' | 'council' | 'synthesis' | 'completed') {
    unifiedPhase.value = p
  }

  function setUnifiedPhaseIndex(index: number, total?: number) {
    unifiedPhaseIndex.value = index
    if (total !== undefined) unifiedPhaseTotal.value = total
  }

  function setMetaPhase(p: string) {
    metaPhase.value = p
  }

  function setMetaCycle(index: number, maxCycles?: number) {
    metaCycleIndex.value = index
    if (maxCycles !== undefined) metaMaxCycles.value = maxCycles
  }

  function setMetaTargetScore(score: number) {
    metaTargetScore.value = score
  }

  function setMetaBestScore(score: number) {
    metaBestScore.value = score
  }

  function setMetaSelectedIntervention(intervention: Record<string, any> | null) {
    metaSelectedIntervention.value = intervention
  }

  function setMetaStopReason(reason: string) {
    metaStopReason.value = reason
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
    isPresetMode,
    isPipelineMode,
    isMetaMode,
    isUnifiedMode,
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
    unifiedPhase,
    unifiedPhaseIndex,
    unifiedPhaseTotal,
    setUnifiedPhase,
    setUnifiedPhaseIndex,
    societyPhase,
    opinionDistribution,
    evaluationMetrics,
    societyActivationProgress,
    setSocietyPhase,
    setOpinionDistribution,
    addPropagationTimestep,
    setPropagationCompleted,
    propagationTimesteps,
    propagationCompleted,
    propagationClusters,
    echoChamberMetrics,
    setEvaluationMetrics,
    setSocietyActivationProgress,
    metaPhase,
    metaCycleIndex,
    metaMaxCycles,
    metaTargetScore,
    metaBestScore,
    metaStopReason,
    metaSelectedIntervention,
    setMetaPhase,
    setMetaCycle,
    setMetaTargetScore,
    setMetaBestScore,
    setMetaSelectedIntervention,
    setMetaStopReason,
    setReportReady,
    setReportSections,
    setReportSectionsState,
    completeReportSection,
    setReportError,
    toSnapshot,
    restoreSnapshot,
  }
})
