<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getSimulation,
  getSimulationReport,
  getSimulationGraph,
  getSimulationGraphHistory,
  getSimulationColonies,
  submitSimulationFollowup,
  rerunSimulation,
  type SimulationResponse,
  type ColonyResponse,
  type GraphSnapshot,
  type EvidenceRef,
  type QualitySummary,
  type SimulationReportResponse,
  type PMBoardReportResponse,
  type RunConfig,
  type SocietyFirstReportResponse,
  type SocietyFirstBacktestResponse,
  type SocietyFirstIntervention,
  type SocietyFirstInterventionEvidence,
  type MetaSimulationReportResponse,
  type MetaInterventionPlan,
  type UnifiedReportResponse,
  type DecisionBrief,
  getTranscript,
  type TranscriptEntry,
} from '../api/client'
import { useForceGraph } from '../composables/useForceGraph'
import DecisionBriefComponent from '../components/DecisionBrief.vue'
import TemporalSlider from '../components/TemporalSlider.vue'
import ProbabilityChart from '../components/ProbabilityChart.vue'
import ScenarioCompare from '../components/ScenarioCompare.vue'
import AgreementHeatmap from '../components/AgreementHeatmap.vue'
import AgentMindView from '../components/AgentMindView.vue'
import MemoryStreamViewer from '../components/MemoryStreamViewer.vue'
import EvaluationDashboard from '../components/EvaluationDashboard.vue'
import ToMMapVisualization from '../components/ToMMapVisualization.vue'
import SocialNetworkDynamics from '../components/SocialNetworkDynamics.vue'
import KnowledgeGraphExplorer from '../components/KnowledgeGraphExplorer.vue'
import { useCognitiveStore } from '../stores/cognitiveStore'
import {
  getDefaultResultsSecondaryTab,
  getResultsPrimaryView,
  getResultsSecondaryTabs,
  type ResultsPrimaryView,
  type ResultsSecondaryTab,
} from './layoutRules'

const route = useRoute()
const router = useRouter()
const simId = route.params.id as string
const ROUND_DURATION_MS = 1200

const sim = ref<SimulationResponse | null>(null)
const report = ref<SimulationReportResponse | null>(null)
const error = ref('')
const loading = ref(true)
const graphContainer = ref<HTMLElement | null>(null)
const graphSnapshots = ref<GraphSnapshot[]>([])
const fallbackGraph = ref<{ nodes: any[]; edges: any[] } | null>(null)
const currentRound = ref(0)
const transitionTargetRound = ref<number | null>(null)
const transitionProgress = ref(0)
const isPlaying = ref(false)
const colonies = ref<ColonyResponse[]>([])
const transcriptEntries = ref<TranscriptEntry[]>([])
const transcriptLoading = ref(false)
const transcriptPhaseFilter = ref<string>('')
const cognitiveStore = useCognitiveStore()
const activeSecondaryTab = ref<ResultsSecondaryTab>('society')
const isCognitiveMode = computed(() => cognitiveStore.cognitiveMode === 'advanced')
const cognitiveSubTab = ref<'mind' | 'memory' | 'evaluation' | 'tom' | 'social' | 'kg'>('mind')
let playbackFrame: number | null = null
let playbackStartedAt: number | null = null

const {
  setFullGraph,
  startGraphTransition,
  updateGraphTransition,
  finishGraphTransition,
  graphError,
} = useForceGraph(graphContainer)

// Follow-up
const followupQuestion = ref('')
const followupAnswers = ref<Array<{ question: string; answer: string; loading?: boolean; evidenceRefs?: EvidenceRef[] }>>([])
const isFollowupLoading = ref(false)
const copyState = ref<'idle' | 'success' | 'error'>('idle')
let copyStateTimer: number | null = null

const isPipelineMode = computed(() => sim.value?.mode === 'pipeline')
const isMetaMode = computed(() => sim.value?.mode === 'meta_simulation')
const societyFirstData = computed<SocietyFirstReportResponse | null>(() => (
  report.value?.type === 'society_first' ? report.value as SocietyFirstReportResponse : null
))
const unifiedReport = computed<UnifiedReportResponse | null>(() => (
  report.value?.type === 'unified' ? report.value as UnifiedReportResponse : null
))
const unifiedCouncil = computed(() => unifiedReport.value?.council || null)
const metaReport = computed<MetaSimulationReportResponse | null>(() => (
  report.value?.type === 'meta_simulation' ? report.value as MetaSimulationReportResponse : null
))
const metaBestCycle = computed(() => {
  const cycles = metaReport.value?.cycles || []
  const candidate = cycles.find(
    (cycle) => cycle.cycle_index === metaReport.value?.final_state?.best_cycle_index,
  )
  return candidate || cycles[cycles.length - 1] || null
})
const societyResult = computed(() => (
  metaReport.value?.society_summary
  || unifiedReport.value?.society_summary
  || societyFirstData.value?.society_summary
  || sim.value?.metadata?.society_result
  || null
))
const meetingReport = computed(() => societyResult.value?.meeting || null)
const societyIssueCandidates = computed(() => (
  metaBestCycle.value?.issue_candidates
  || societyFirstData.value?.issue_candidates
  || []
))
const selectedSocietyIssues = computed(() => (
  metaBestCycle.value?.selected_issues
  || societyFirstData.value?.selected_issues
  || []
))
interface SocietyInterventionViewModel {
  interventionId: string
  label: string
  modeClass: 'observed' | 'heuristic'
  modeLabel: string
  description: string
  issues: string[]
  expectedEffect: string
  isObserved: boolean
  observedUplift?: number | null
  observedDownside?: number | null
  uncertainty?: number | null
  supportingEvidence: SocietyFirstInterventionEvidence[]
}

function normalizeSocietyIntervention(
  intervention: SocietyFirstIntervention | MetaInterventionPlan,
): SocietyInterventionViewModel {
  if ('change_summary' in intervention) {
    const isObserved = intervention.comparison_mode === 'observed'
    return {
      interventionId: intervention.intervention_id,
      label: intervention.label,
      modeClass: isObserved ? 'observed' : 'heuristic',
      modeLabel: isObserved ? '実測比較' : '仮説比較',
      description: intervention.change_summary,
      issues: intervention.affected_issues || [],
      expectedEffect: intervention.expected_effect,
      isObserved,
      observedUplift: intervention.observed_uplift,
      observedDownside: intervention.observed_downside,
      uncertainty: intervention.uncertainty,
      supportingEvidence: intervention.supporting_evidence || [],
    }
  }

  return {
    interventionId: intervention.intervention_id,
    label: intervention.label,
    modeClass: 'heuristic',
    modeLabel: intervention.change_type || '仮説比較',
    description: intervention.hypothesis,
    issues: intervention.target_issues || [],
    expectedEffect: intervention.expected_effect,
    isObserved: false,
    supportingEvidence: [],
  }
}

const societyInterventions = computed<SocietyInterventionViewModel[]>(() => {
  const metaInterventions = metaReport.value?.intervention_history
  if (metaInterventions?.length) {
    return metaInterventions.map(normalizeSocietyIntervention)
  }

  const societyFirstInterventions = societyFirstData.value?.intervention_comparison
  if (societyFirstInterventions?.length) {
    return societyFirstInterventions.map(normalizeSocietyIntervention)
  }

  return []
})
const societyBacktest = computed<SocietyFirstBacktestResponse | null>(() => societyFirstData.value?.backtest || null)
const hasScenarios = computed(() => (report.value?.scenarios?.length ?? 0) > 0)
const hasPmBoard = computed(() => {
  if (isPipelineMode.value) return !!report.value?.pm_board
  if (isMetaMode.value) return !!metaReport.value?.pm_board
  return !!(sim.value?.mode === 'pm_board' && report.value?.sections)
})
const reportFailureMessage = computed(() => {
  const progress = sim.value?.metadata?.report_progress
  if (progress?.status !== 'failed') return ''
  return progress?.last_error || 'レポート生成に失敗しました。シナリオ結果は引き続き参照できます。'
})
const pmBoardData = computed(() => {
  if (isPipelineMode.value && report.value?.type === 'pipeline') {
    return report.value.pm_board || null
  }
  if (report.value?.type === 'meta_simulation') return report.value.pm_board || null
  if (report.value?.type === 'pm_board') return report.value as PMBoardReportResponse
  return null
})
const decisionBriefData = computed<DecisionBrief | null>(() => {
  if (report.value?.decision_brief) return report.value.decision_brief
  const reportSections = report.value?.sections as Record<string, any> | undefined
  if (
    reportSections
    && typeof reportSections === 'object'
    && reportSections.decision_brief
  ) {
    return reportSections.decision_brief as DecisionBrief
  }
  if (pmBoardData.value?.decision_brief) return pmBoardData.value.decision_brief
  return null
})
const hasDecisionBrief = computed(() => !!decisionBriefData.value)
const normalizedScenarios = computed(() => (
  ((report.value?.type === 'pipeline' || report.value?.type === 'swarm' || report.value?.type === 'society_first' || report.value?.type === 'meta_simulation')
    ? report.value.scenarios || []
    : []
  ).map((s) => ({
    description: s.description,
    scenarioScore: s.scenario_score ?? s.probability ?? 0,
    ci: s.ci ?? [0, 1],
    supportRatio: s.support_ratio ?? s.agreement_ratio ?? 0,
    modelConfidenceMean: s.model_confidence_mean ?? s.mean_confidence ?? 0,
    supportingColonies: s.supporting_colonies ?? 0,
    totalColonies: s.total_colonies ?? 0,
    claimCount: s.claim_count ?? 0,
    calibratedProbability: s.calibrated_probability ?? null,
  }))
))
const reportQuality = computed<QualitySummary | null>(() => {
  if (report.value?.quality) return report.value.quality
  if (pmBoardData.value?.quality) return pmBoardData.value.quality
  return null
})
const reportEvidenceRefs = computed<EvidenceRef[]>(() => report.value?.evidence_refs || [])
const runConfig = computed<RunConfig | null>(() => {
  if (report.value?.run_config) return report.value.run_config
  if (pmBoardData.value?.run_config) return pmBoardData.value.run_config
  return null
})
const verification = computed(() => report.value?.verification ?? pmBoardData.value?.verification ?? null)
const reportQualityMessage = computed(() => {
  const quality = reportQuality.value
  if (!quality) return ''
  if (quality.status === 'verified') return '文書根拠付きで出力されています。'
  if (quality.status === 'unsupported') {
    return quality.unsupported_reason || quality.fallback_reason || '品質基準を満たしていないため参考用途に限定してください。'
  }
  if (quality.trust_level === 'low_trust') {
    return 'プロンプト入力のみを根拠にした低信頼の出力です。文書添付時より精度保証は弱くなります。'
  }
  return quality.fallback_reason || (quality as any).unsupported_reason || '品質基準を満たしていないため参考用途に限定してください。'
})
const evidenceSummary = computed(() => {
  const quality = reportQuality.value
  if (!quality) return ''
  return `mode=${quality.evidence_mode || runConfig.value?.evidence_mode || 'prefer'} · document=${quality.document_refs_count ?? 0} · refs=${quality.evidence_refs_count}`
})

const reportText = computed(() => {
  if (typeof report.value?.content === 'string') return report.value.content
  return ''
})
const reportJson = computed(() => (
  report.value ? JSON.stringify(report.value, null, 2) : ''
))
const agreementMatrix = computed(() => {
  if (!report.value?.agreement_matrix) return null
  return report.value.agreement_matrix as { colony_ids: string[]; matrix: number[][] }
})
const canCopyReport = computed(() => reportText.value.trim().length > 0)
const snapshotByRound = computed(() => new Map(graphSnapshots.value.map((snapshot) => [snapshot.round, snapshot])))
const displayedGraphData = computed(() => {
  const activeRound = transitionTargetRound.value !== null && transitionProgress.value >= 0.5
    ? transitionTargetRound.value
    : currentRound.value
  return snapshotByRound.value.get(activeRound) ?? fallbackGraph.value
})
const kgEntities = computed(() => (
  (displayedGraphData.value?.nodes || []).map((node: any) => ({
    id: String(node.id),
    label: node.label || String(node.id),
    type: node.type || 'unknown',
    description: node.group ? `Group: ${node.group}` : `${node.type || 'unknown'} entity`,
    community: node.group || undefined,
    aliases: [],
  }))
))
const kgRelations = computed(() => (
  (displayedGraphData.value?.edges || []).map((edge: any) => ({
    source: String(edge.source),
    target: String(edge.target),
    type: edge.relation_type || 'related_to',
    confidence: Math.max(0, Math.min(Number(edge.weight ?? 0.5), 1)),
  }))
))
const kgCommunities = computed(() => {
  const groups = new Map<string, string[]>()
  for (const node of displayedGraphData.value?.nodes || []) {
    if (!node.group) continue
    const members = groups.get(node.group) || []
    members.push(node.label || String(node.id))
    groups.set(node.group, members)
  }
  return Array.from(groups.entries()).map(([community, members]) => ({
    community,
    summary: `${members.length} entities`,
    members,
  }))
})
const sliderDisplayValue = computed(() => {
  if (transitionTargetRound.value === null) return currentRound.value
  return currentRound.value + transitionProgress.value
})

function backtestVerdictLabel(verdict?: string | null) {
  if (verdict === 'hit') return 'Hit'
  if (verdict === 'partial_hit') return 'Partial'
  if (verdict === 'miss') return 'Miss'
  return 'n/a'
}

function backtestVerdictClass(verdict?: string | null) {
  if (verdict === 'hit') return 'verdict-hit'
  if (verdict === 'partial_hit') return 'verdict-partial'
  return 'verdict-miss'
}

const totalRounds = computed(() => {
  if (isMetaMode.value) return 0
  if (graphSnapshots.value.length === 0) return 0
  return graphSnapshots.value[graphSnapshots.value.length - 1].round
})
const showGraphViews = computed(() => !isMetaMode.value)
const layoutContext = computed(() => ({
  mode: sim.value?.mode,
  hasScenarios: hasScenarios.value,
  hasDecisionBrief: hasDecisionBrief.value,
  hasPmBoard: hasPmBoard.value,
  hasSociety: !!societyResult.value,
  hasGraph: showGraphViews.value,
  hasEvidence: reportEvidenceRefs.value.length > 0,
  hasRaw: !!report.value,
  hasTranscript: sim.value?.mode === 'unified' || sim.value?.mode === 'society' || sim.value?.mode === 'society_first',
}))
const primaryViewKind = computed<ResultsPrimaryView>(() => getResultsPrimaryView(layoutContext.value))
const secondaryTabs = computed<ResultsSecondaryTab[]>(() => getResultsSecondaryTabs(layoutContext.value))
const primaryEyebrow = computed(() => {
  if (primaryViewKind.value === 'scenarios') return 'Scenario Workspace'
  if (primaryViewKind.value === 'decision_brief') return 'Decision Workspace'
  return 'Report Workspace'
})
const primaryTitle = computed(() => {
  if (primaryViewKind.value === 'scenarios') return 'シナリオ比較を起点に結果を読む'
  if (primaryViewKind.value === 'decision_brief') return '意思決定の結論と次アクションを読む'
  return '本文レポートを主軸に分析結果を読む'
})
const primaryDescription = computed(() => {
  if (primaryViewKind.value === 'scenarios') {
    return '最も起こりやすいシナリオ、支持率、信頼区間をまとめて確認できます。'
  }
  if (primaryViewKind.value === 'decision_brief') {
    return 'Recommendation、判断根拠、直近アクションを先に確認できる構成です。'
  }
  return '要約と本文を中心に、補助分析は右ペインから切り替えて参照できます。'
})
const primaryScenarioSummary = computed(() => normalizedScenarios.value[0] || null)
const secondaryTabLabels: Record<ResultsSecondaryTab, string> = {
  pm: 'PM',
  society: 'Society',
  transcript: 'Transcript',
  evidence: 'Evidence',
}

function stopPlaybackLoop() {
  if (playbackFrame !== null) {
    cancelAnimationFrame(playbackFrame)
    playbackFrame = null
  }
  playbackStartedAt = null
}

function resetTransitionState() {
  transitionTargetRound.value = null
  transitionProgress.value = 0
  playbackStartedAt = null
}

function showRound(round: number) {
  const snapshot = snapshotByRound.value.get(round)
  if (!snapshot) return false

  currentRound.value = round
  resetTransitionState()
  setFullGraph(snapshot.nodes, snapshot.edges)
  return true
}

function stopPlayback(round = currentRound.value) {
  stopPlaybackLoop()
  isPlaying.value = false
  showRound(round)
}

function queueNextTransition(fromRound: number) {
  stopPlaybackLoop()
  playbackFrame = requestAnimationFrame(() => {
    if (!isPlaying.value) return
    beginRoundTransition(fromRound)
  })
}

function stepPlayback(timestamp: number) {
  if (!isPlaying.value || transitionTargetRound.value === null) return

  if (playbackStartedAt === null) {
    playbackStartedAt = timestamp
  }

  const rawProgress = Math.min((timestamp - playbackStartedAt) / ROUND_DURATION_MS, 1)
  transitionProgress.value = rawProgress
  updateGraphTransition(rawProgress)

  if (rawProgress < 1) {
    playbackFrame = requestAnimationFrame(stepPlayback)
    return
  }

  finishGraphTransition()
  currentRound.value = transitionTargetRound.value
  resetTransitionState()

  if (currentRound.value < totalRounds.value) {
    queueNextTransition(currentRound.value)
    return
  }

  isPlaying.value = false
}

function beginRoundTransition(fromRound: number) {
  const fromSnapshot = snapshotByRound.value.get(fromRound)
  const toSnapshot = snapshotByRound.value.get(fromRound + 1)
  if (!toSnapshot) {
    stopPlayback(fromRound)
    return
  }

  stopPlaybackLoop()
  currentRound.value = fromRound
  transitionTargetRound.value = toSnapshot.round
  transitionProgress.value = 0
  if (fromSnapshot) {
    startGraphTransition(fromSnapshot.nodes, fromSnapshot.edges, toSnapshot.nodes, toSnapshot.edges)
  } else {
    setFullGraph(toSnapshot.nodes, toSnapshot.edges)
  }
  playbackFrame = requestAnimationFrame(stepPlayback)
}

function startPlayback() {
  if (graphSnapshots.value.length <= 1) return

  const startRound = currentRound.value >= totalRounds.value ? 0 : currentRound.value
  if (!showRound(startRound)) return

  isPlaying.value = true
  queueNextTransition(startRound)
}

onMounted(async () => {
  try {
    sim.value = await getSimulation(simId)

    const [reportData, graphHistory] = await Promise.all([
      getSimulationReport(simId).catch(() => null),
      getSimulationGraphHistory(simId).catch(() => []),
    ])

    report.value = reportData
    graphSnapshots.value = graphHistory

    // レポートが未取得かつシミュレーション完了済みなら数秒後にリトライ
    if (!reportData && sim.value?.status === 'completed') {
      setTimeout(async () => {
        try {
          report.value = await getSimulationReport(simId)
        } catch { /* ignore */ }
      }, 3000)
    }

    activeSecondaryTab.value = getDefaultResultsSecondaryTab(layoutContext.value)

    // Colony データ取得
    if (hasScenarios.value || sim.value.swarm_id) {
      colonies.value = await getSimulationColonies(simId).catch(() => [])
    }

    // Transcript 取得 (unified/society modes)
    if (layoutContext.value.hasTranscript) {
      loadTranscript()
    }

    // 最新グラフ表示
    if (showGraphViews.value && graphHistory.length > 0) {
      const latest = graphHistory[graphHistory.length - 1]
      currentRound.value = latest.round
      fallbackGraph.value = { nodes: latest.nodes, edges: latest.edges }
      await nextTick()
      setFullGraph(latest.nodes, latest.edges)
    } else if (showGraphViews.value) {
      const graphData = await getSimulationGraph(simId).catch(() => null)
      if (graphData?.nodes?.length) {
        fallbackGraph.value = { nodes: graphData.nodes, edges: graphData.edges }
        await nextTick()
        setFullGraph(graphData.nodes, graphData.edges)
      }
    }
  } catch (e) {
    error.value = 'データの読み込みに失敗しました。'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  stopPlaybackLoop()
  if (copyStateTimer !== null) {
    window.clearTimeout(copyStateTimer)
  }
})

function onRoundChange(round: number) {
  stopPlaybackLoop()
  isPlaying.value = false
  showRound(round)
}

function onPlayingChange(playing: boolean) {
  if (playing) {
    startPlayback()
    return
  }

  const snapRound = transitionTargetRound.value !== null && transitionProgress.value >= 0.5
    ? transitionTargetRound.value
    : currentRound.value
  stopPlayback(snapRound)
}

async function handleFollowup() {
  if (!followupQuestion.value.trim() || isFollowupLoading.value) return
  isFollowupLoading.value = true
  const question = followupQuestion.value
  followupQuestion.value = ''
  followupAnswers.value.push({ question, answer: '', loading: true })
  const idx = followupAnswers.value.length - 1

  try {
    const result = await submitSimulationFollowup(simId, question)
    followupAnswers.value[idx] = {
      question,
      answer: result.answer || '回答を生成中...',
      evidenceRefs: result.evidence_refs || [],
    }
  } catch {
    followupAnswers.value[idx] = { question, answer: 'エラーが発生しました。' }
  } finally {
    isFollowupLoading.value = false
  }
}

async function handleRerun() {
  try {
    const result = await rerunSimulation(simId)
    router.push(`/sim/${result.id}`)
  } catch {
    alert('再実行に失敗しました。')
  }
}

function setCopyState(state: 'idle' | 'success' | 'error') {
  copyState.value = state

  if (copyStateTimer !== null) {
    window.clearTimeout(copyStateTimer)
    copyStateTimer = null
  }

  if (state !== 'idle') {
    copyStateTimer = window.setTimeout(() => {
      copyState.value = 'idle'
      copyStateTimer = null
    }, 2000)
  }
}

async function copyReportText() {
  if (!canCopyReport.value) return

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(reportText.value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = reportText.value
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      textarea.style.pointerEvents = 'none'
      document.body.appendChild(textarea)
      textarea.select()

      const copied = document.execCommand('copy')
      document.body.removeChild(textarea)

      if (!copied) {
        throw new Error('clipboard copy failed')
      }
    }

    setCopyState('success')
  } catch {
    setCopyState('error')
  }
}

async function loadTranscript(phase?: string) {
  transcriptLoading.value = true
  try {
    const data = await getTranscript(simId, phase || undefined)
    transcriptEntries.value = data.entries
  } catch {
    transcriptEntries.value = []
  } finally {
    transcriptLoading.value = false
  }
}

const filteredTranscript = computed(() => {
  if (!transcriptPhaseFilter.value) return transcriptEntries.value
  return transcriptEntries.value.filter(e => e.phase === transcriptPhaseFilter.value)
})

function renderMarkdown(content: string): string {
  return content
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^---$/gm, '<hr/>')
    .replace(/\n\n/g, '</p><p>')
}
</script>

<template>
  <div class="results-page">
    <div v-if="loading" class="loading-state">
      <div class="loading-dots"><span></span><span></span><span></span></div>
      <p>読み込み中...</p>
    </div>

    <template v-else>
      <!-- Header -->
      <div class="result-header">
        <div class="header-left">
          <h2>Analysis Results</h2>
          <span v-if="sim" class="header-meta">
            {{ sim.template_name || 'プロンプト実行' }} · {{ sim.execution_profile }}
          </span>
        </div>
        <div class="header-actions">
          <button class="btn btn-ghost" @click="handleRerun">再実行</button>
          <router-link :to="`/sim/${simId}`" class="btn btn-ghost">実行画面</router-link>
        </div>
      </div>

      <div v-if="error" class="error-banner">{{ error }}</div>
      <div v-if="reportFailureMessage" class="error-banner">
        {{ reportFailureMessage }}
      </div>
      <div
        v-if="reportQuality"
        data-testid="quality-banner"
        class="quality-banner"
        :class="`quality-${reportQuality.status}`"
      >
        <strong>
          {{
            reportQuality.status === 'verified'
              ? 'Verified'
              : reportQuality.status === 'draft'
                ? 'Draft'
                : 'Unsupported'
          }}
        </strong>
        <span>{{ reportQualityMessage }}</span>
        <span v-if="evidenceSummary" class="quality-meta">{{ evidenceSummary }}</span>
        <span v-if="verification" class="quality-meta">
          verification={{ verification.status }} ({{ (verification.score * 100).toFixed(0) }}%)
        </span>
      </div>

      <div v-if="reportEvidenceRefs.length" class="evidence-panel">
        <div class="section-header">
          <h3 class="section-title">Evidence</h3>
          <span class="section-badge">{{ reportEvidenceRefs.length }} refs</span>
        </div>
        <div class="evidence-list">
          <div v-for="ref in reportEvidenceRefs.slice(0, 6)" :key="`${ref.source_id}:${ref.char_start}`" class="evidence-card">
            <div class="evidence-card-top">
              <span class="evidence-label">{{ ref.label }}</span>
              <span class="evidence-type">{{ ref.source_type }}</span>
            </div>
            <p class="evidence-excerpt">{{ ref.excerpt }}</p>
          </div>
        </div>
      </div>

      <!-- Stats -->
      <div v-if="hasScenarios && report" class="stats-row">
        <div class="stat-card">
          <span class="stat-label">多様性スコア</span>
          <span class="stat-value">{{ ((report.diversity_score || 0) * 100).toFixed(0) }}%</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">エントロピー</span>
          <span class="stat-value">{{ (report.entropy || 0).toFixed(2) }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">シナリオ数</span>
          <span class="stat-value">{{ report.scenarios?.length || 0 }}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Colony</span>
          <span class="stat-value">{{ colonies.length }}</span>
        </div>
      </div>

      <div class="results-layout results-workspace">
        <div class="results-main">
          <div class="workspace-hero" data-testid="results-primary-view">
            <div class="workspace-copy">
              <span class="workspace-eyebrow">{{ primaryEyebrow }}</span>
              <h3 class="workspace-title">{{ primaryTitle }}</h3>
              <p class="workspace-description">{{ primaryDescription }}</p>
            </div>
            <div class="workspace-highlights">
              <div v-if="primaryViewKind === 'scenarios' && primaryScenarioSummary" class="workspace-highlight-card">
                <span class="workspace-highlight-label">Top Scenario</span>
                <strong class="workspace-highlight-value">{{ (primaryScenarioSummary.scenarioScore * 100).toFixed(1) }}%</strong>
                <p>{{ primaryScenarioSummary.description }}</p>
              </div>
              <div v-else-if="primaryViewKind === 'decision_brief' && decisionBriefData" class="workspace-highlight-card">
                <span class="workspace-highlight-label">Recommendation</span>
                <strong class="workspace-highlight-value">{{ decisionBriefData.recommendation }}</strong>
                <p>{{ decisionBriefData.decision_summary }}</p>
              </div>
              <div v-else class="workspace-highlight-card">
                <span class="workspace-highlight-label">Report</span>
                <strong class="workspace-highlight-value">{{ reportText ? 'Ready' : 'Pending' }}</strong>
                <p>{{ reportText ? '本文レポートを基準に読み進めます。' : '本文がない場合は補助分析を主に参照します。' }}</p>
              </div>
            </div>
          </div>

          <div v-if="primaryViewKind === 'scenarios'" class="tab-panel primary-panel">
            <ScenarioCompare v-if="report?.scenarios" :scenarios="normalizedScenarios" />

            <div v-if="agreementMatrix?.matrix?.length" class="mt-section">
              <h3 class="content-title">合意ヒートマップ</h3>
              <AgreementHeatmap
                :matrix="agreementMatrix"
                :colonies="colonies.map((c: any) => ({
                  id: c.id,
                  colonyIndex: c.colony_index,
                  perspectiveId: c.perspective_id,
                  perspectiveLabel: c.perspective_label,
                  temperature: c.temperature,
                  adversarial: c.adversarial,
                  status: c.status,
                  currentRound: c.current_round,
                  totalRounds: c.total_rounds,
                  eventCount: 0,
                }))"
              />
            </div>

            <div class="mt-section">
              <h3 class="content-title">スコア分布チャート</h3>
              <ProbabilityChart :scenarios="normalizedScenarios" />
            </div>

            <div v-if="decisionBriefData" class="workspace-inline-card">
              <div class="section-header">
                <h3 class="section-title">Decision Snapshot</h3>
                <span class="section-badge">{{ decisionBriefData.recommendation }}</span>
              </div>
              <p class="workspace-inline-copy">{{ decisionBriefData.decision_summary }}</p>
              <ul v-if="decisionBriefData.recommended_actions?.length" class="workspace-inline-list">
                <li v-for="(action, index) in decisionBriefData.recommended_actions.slice(0, 3)" :key="`${action.action}-${index}`">
                  {{ action.action }}
                </li>
              </ul>
            </div>

            <div v-if="reportText" class="report-panel">
              <div class="report-toolbar">
                <p class="report-toolbar-note">本文も併せて確認できます。</p>
                <button
                  class="btn btn-ghost report-copy-btn"
                  :disabled="!canCopyReport"
                  @click="copyReportText"
                >
                  {{
                    copyState === 'success'
                      ? 'コピー済み'
                      : copyState === 'error'
                        ? 'コピー失敗'
                        : 'テキストをコピー'
                  }}
                </button>
              </div>
              <div class="report-content" v-html="renderMarkdown(reportText)"></div>
            </div>
          </div>

          <div v-else-if="primaryViewKind === 'decision_brief' && decisionBriefData" class="tab-panel primary-panel">
            <DecisionBriefComponent :brief="decisionBriefData" />

            <div v-if="unifiedCouncil?.participants?.length" class="brief-council-section">
              <h4 class="brief-council-title">評議会メンバー</h4>
              <div class="brief-council-grid">
                <div
                  v-for="(p, i) in unifiedCouncil.participants"
                  :key="i"
                  class="brief-council-chip"
                  :class="p.role"
                >
                  {{ p.display_name }}
                  <span v-if="p.stance" class="brief-council-stance">{{ p.stance }}</span>
                </div>
              </div>
              <div v-if="unifiedCouncil.devil_advocate_summary" class="brief-devil-advocate">
                <h4 class="brief-council-title">反証役サマリー</h4>
                <p>{{ unifiedCouncil.devil_advocate_summary }}</p>
              </div>
            </div>

            <div v-if="reportText" class="report-panel">
              <div class="report-toolbar">
                <p class="report-toolbar-note">本文レポートも下に保持します。</p>
              </div>
              <div class="report-content" v-html="renderMarkdown(reportText)"></div>
            </div>
          </div>

          <div v-else class="tab-panel primary-panel">
            <div v-if="decisionBriefData" class="workspace-inline-card">
              <div class="section-header">
                <h3 class="section-title">Decision Snapshot</h3>
                <span class="section-badge">{{ decisionBriefData.recommendation }}</span>
              </div>
              <p class="workspace-inline-copy">{{ decisionBriefData.decision_summary }}</p>
            </div>

            <div v-if="metaReport" class="meta-report-panel">
              <div class="meta-summary-grid">
                <div class="stat-card">
                  <span class="stat-label">最良サイクル</span>
                  <span class="stat-value">{{ metaReport.final_state?.best_cycle_index || 0 }}</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">最良スコア</span>
                  <span class="stat-value">{{ ((metaReport.final_state?.best_objective_score || 0) * 100).toFixed(0) }}%</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">停止理由</span>
                  <span class="stat-value meta-stop-reason">{{ metaReport.final_state?.stop_reason || 'unknown' }}</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">介入履歴</span>
                  <span class="stat-value">{{ metaReport.intervention_history?.length || 0 }}</span>
                </div>
              </div>
            </div>

            <div v-if="reportText" class="report-panel">
              <div class="report-toolbar">
                <p class="report-toolbar-note">統合分析レポートをプレーンテキストでコピーできます。</p>
                <button
                  class="btn btn-ghost report-copy-btn"
                  :disabled="!canCopyReport"
                  @click="copyReportText"
                >
                  {{
                    copyState === 'success'
                      ? 'コピー済み'
                      : copyState === 'error'
                        ? 'コピー失敗'
                        : 'テキストをコピー'
                  }}
                </button>
              </div>
              <div class="report-content" v-html="renderMarkdown(reportText)"></div>
            </div>
            <div v-else-if="hasScenarios && report?.scenarios">
              <h3 class="content-title">シナリオスコア分布</h3>
              <ProbabilityChart :scenarios="normalizedScenarios" />
            </div>
            <div v-else class="empty-state">レポートが見つかりません</div>
          </div>
        </div>

        <div class="results-side">
          <div class="side-card secondary-switcher">
            <div class="side-header">
              <h3>Details</h3>
            </div>
            <div class="secondary-switcher-buttons">
              <button
                v-for="tab in secondaryTabs"
                :key="tab"
                class="subtab-btn"
                :class="{ active: activeSecondaryTab === tab }"
                @click="activeSecondaryTab = tab"
              >
                {{ secondaryTabLabels[tab] }}
              </button>
            </div>
          </div>

          <div v-if="activeSecondaryTab === 'graph' && showGraphViews" class="side-card">
            <div class="side-header">
              <h3>3D Graph</h3>
            </div>
            <div ref="graphContainer" class="graph-snapshot-large"></div>
            <div v-if="graphError" class="graph-error-note">{{ graphError }}</div>
            <TemporalSlider
              v-if="graphSnapshots.length > 1"
              :total-rounds="totalRounds"
              :model-value="currentRound"
              :display-value="sliderDisplayValue"
              :playing="isPlaying"
              @update:model-value="onRoundChange"
              @update:playing="onPlayingChange"
            />

            <div v-if="isCognitiveMode" class="cognitive-subtabs">
              <button
                v-for="sub in [
                  { key: 'mind', label: '認知状態' },
                  { key: 'memory', label: '記憶' },
                  { key: 'evaluation', label: '評価' },
                  { key: 'tom', label: 'ToM' },
                  { key: 'social', label: '社会NW' },
                  { key: 'kg', label: 'KG探索' },
                ]"
                :key="sub.key"
                class="subtab-btn"
                :class="{ active: cognitiveSubTab === sub.key }"
                @click="cognitiveSubTab = sub.key as any"
              >
                {{ sub.label }}
              </button>
            </div>
            <div v-if="isCognitiveMode" class="cognitive-content">
              <AgentMindView v-if="cognitiveSubTab === 'mind'" />
              <MemoryStreamViewer v-if="cognitiveSubTab === 'memory'" />
              <EvaluationDashboard v-if="cognitiveSubTab === 'evaluation'" />
              <ToMMapVisualization v-if="cognitiveSubTab === 'tom'" />
              <SocialNetworkDynamics v-if="cognitiveSubTab === 'social'" />
              <KnowledgeGraphExplorer
                v-if="cognitiveSubTab === 'kg'"
                :entities="kgEntities"
                :relations="kgRelations"
                :communities="kgCommunities"
              />
            </div>
          </div>

          <div v-if="activeSecondaryTab === 'society' && societyResult" class="side-card">
            <div class="side-header">
              <h3>Society Summary</h3>
            </div>
            <div class="society-section">
              <div class="society-stats-row">
                <span class="society-stat">
                  <span class="society-stat-label">人口</span>
                  <span class="society-stat-value">{{ (societyResult.population_count ?? societyResult.aggregation?.total_submitted)?.toLocaleString() || 'n/a' }}</span>
                </span>
                <span class="society-stat">
                  <span class="society-stat-label">選抜</span>
                  <span class="society-stat-value">{{ societyResult.selected_count ?? societyResult.aggregation?.total_respondents ?? 'n/a' }}</span>
                </span>
                <span class="society-stat">
                  <span class="society-stat-label">平均信頼度</span>
                  <span class="society-stat-value">{{ ((societyResult.aggregation?.average_confidence || 0) * 100).toFixed(1) }}%</span>
                </span>
              </div>
              <div v-if="societyResult.aggregation?.top_concerns?.length" class="society-section">
                <h4 class="society-section-title">主要な懸念</h4>
                <ul class="society-list">
                  <li v-for="concern in societyResult.aggregation.top_concerns" :key="concern">{{ concern }}</li>
                </ul>
              </div>
              <div v-if="societyIssueCandidates.length" class="society-section">
                <h4 class="society-section-title">重要論点ランキング</h4>
                <div class="society-issue-grid">
                  <div v-for="issue in societyIssueCandidates.slice(0, 3)" :key="issue.issue_id" class="society-issue-card">
                    <div class="society-issue-top">
                      <span class="society-issue-label">{{ issue.label }}</span>
                      <span class="society-issue-score">{{ (issue.selection_score * 100).toFixed(0) }}</span>
                    </div>
                    <p class="society-issue-desc">{{ issue.description }}</p>
                  </div>
                </div>
              </div>
              <div v-if="selectedSocietyIssues.length" class="society-section">
                <h4 class="society-section-title">選抜した Issue Colony</h4>
                <div class="society-chip-row">
                  <span v-for="issue in selectedSocietyIssues" :key="issue.issue_id" class="society-chip">
                    {{ issue.label }}
                  </span>
                </div>
              </div>
              <div v-if="societyInterventions.length" class="society-section">
                <h4 class="society-section-title">介入比較</h4>
                <div class="society-intervention-grid">
                  <div v-for="intervention in societyInterventions" :key="intervention.interventionId" class="society-intervention-card">
                    <div class="society-intervention-top">
                      <span class="society-intervention-label">{{ intervention.label }}</span>
                      <span class="society-intervention-effect" :class="intervention.modeClass">{{ intervention.modeLabel }}</span>
                    </div>
                    <p class="society-intervention-desc">{{ intervention.description }}</p>
                    <p class="society-intervention-issues">対象: {{ intervention.issues.join(', ') }}</p>
                    <p class="society-intervention-hint">{{ intervention.expectedEffect }}</p>
                  </div>
                </div>
              </div>
              <div v-if="societyBacktest" class="society-section">
                <h4 class="society-section-title">Backtest</h4>
                <div v-if="societyBacktest.summary.case_count" class="society-backtest-summary">
                  <div class="society-metric-card">
                    <span class="society-metric-label">historical cases</span>
                    <span class="society-metric-score">{{ societyBacktest.summary.case_count }}</span>
                  </div>
                  <div class="society-metric-card">
                    <span class="society-metric-label">hit rate</span>
                    <span class="society-metric-score">{{ (societyBacktest.summary.hit_rate * 100).toFixed(0) }}%</span>
                  </div>
                  <div class="society-metric-card">
                    <span class="society-metric-label">issue hit rate</span>
                    <span class="society-metric-score">{{ (societyBacktest.summary.issue_hit_rate * 100).toFixed(0) }}%</span>
                  </div>
                </div>
                <div v-if="societyBacktest.summary.case_count" class="society-backtest-grid">
                  <div v-for="historicalCase in societyBacktest.cases" :key="historicalCase.case_id" class="society-backtest-card">
                    <div class="society-backtest-top">
                      <div class="society-backtest-title">{{ historicalCase.title }}</div>
                      <span
                        v-if="historicalCase.best_match"
                        class="society-verdict-badge"
                        :class="backtestVerdictClass(historicalCase.best_match.verdict)"
                      >
                        {{ backtestVerdictLabel(historicalCase.best_match.verdict) }}
                      </span>
                    </div>
                    <p class="society-backtest-outcome">{{ historicalCase.outcome.summary || historicalCase.outcome.actual_scenario }}</p>
                  </div>
                </div>
              </div>
              <div v-if="meetingReport" class="society-section">
                <h4 class="society-section-title">Meeting Layer</h4>
                <p class="society-meeting-summary">{{ meetingReport.summary }}</p>
                <div v-if="meetingReport.participants?.length" class="society-participants-grid">
                  <div v-for="(p, i) in meetingReport.participants" :key="i" class="society-participant-chip" :class="p.role">
                    {{ p.display_name || p.expertise || '参加者' }}
                    <span v-if="p.stance" class="participant-stance-tag">{{ p.stance }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="activeSecondaryTab === 'transcript'" class="side-card">
            <div class="side-header">
              <h3>Transcript</h3>
              <span class="section-badge">{{ filteredTranscript.length }}件</span>
            </div>
            <div class="transcript-filters">
              <button
                v-for="f in [
                  { key: '', label: '全て' },
                  { key: 'activation', label: '活性化' },
                  { key: 'meeting', label: '議論' },
                ]"
                :key="f.key"
                class="subtab-btn"
                :class="{ active: transcriptPhaseFilter === f.key }"
                @click="transcriptPhaseFilter = f.key"
              >
                {{ f.label }}
              </button>
            </div>
            <div v-if="transcriptLoading" class="transcript-loading">読み込み中...</div>
            <div v-else-if="filteredTranscript.length === 0" class="empty-state">
              トランスクリプトがありません
            </div>
            <div v-else class="transcript-list">
              <div
                v-for="entry in filteredTranscript"
                :key="entry.id"
                class="transcript-entry"
                :class="{ 'transcript-stance-changed': entry.stance_changed }"
              >
                <div class="transcript-meta">
                  <span class="transcript-name">{{ entry.participant_name }}</span>
                  <span class="transcript-phase-badge">{{ entry.phase === 'activation' ? '活性化' : `R${entry.round_number}` }}</span>
                  <span v-if="entry.stance" class="transcript-stance">{{ entry.stance }}</span>
                </div>
                <p class="transcript-text">{{ entry.content_text }}</p>
                <p v-if="entry.addressed_to" class="transcript-address">→ {{ entry.addressed_to }}</p>
              </div>
            </div>
          </div>

          <div v-if="activeSecondaryTab === 'pm' && pmBoardData" class="side-card">
            <div class="side-header">
              <h3>PM Evaluation</h3>
            </div>
            <div class="pm-board-result">
              <div v-if="pmBoardData.sections.core_question" class="pm-section">
                <h3 class="pm-section-title">核心質問</h3>
                <p class="pm-section-content">{{ pmBoardData.sections.core_question }}</p>
              </div>
              <div v-if="pmBoardData.sections.assumptions?.length" class="pm-section">
                <h3 class="pm-section-title">主要前提</h3>
                <div v-for="(a, i) in pmBoardData.sections.assumptions.slice(0, 3)" :key="i" class="pm-card">
                  <div class="pm-card-header">
                    <span class="pm-card-label">{{ a.assumption }}</span>
                    <span class="pm-confidence">{{ (a.confidence * 100).toFixed(0) }}%</span>
                  </div>
                  <p v-if="a.evidence" class="pm-card-detail">根拠: {{ a.evidence }}</p>
                </div>
              </div>
              <div v-if="pmBoardData.sections.uncertainties?.length" class="pm-section">
                <h3 class="pm-section-title">不確実性</h3>
                <div v-for="(u, i) in pmBoardData.sections.uncertainties.slice(0, 3)" :key="i" class="pm-card">
                  <div class="pm-card-header">
                    <span class="pm-card-label">{{ u.uncertainty }}</span>
                    <span class="pm-risk-badge" :class="'risk-' + u.risk_level">{{ u.risk_level }}</span>
                  </div>
                  <p v-if="u.validation_method" class="pm-card-detail">検証方法: {{ u.validation_method }}</p>
                </div>
              </div>
              <div v-if="pmBoardData.sections.top_5_actions?.length" class="pm-section">
                <h3 class="pm-section-title">今すぐやるべきアクション</h3>
                <div v-for="(action, idx) in pmBoardData.sections.top_5_actions" :key="idx" class="pm-card pm-action">
                  <div class="pm-action-header">
                    <span class="pm-action-number">{{ Number(idx) + 1 }}</span>
                    <span class="pm-card-label">{{ action.action }}</span>
                  </div>
                  <p v-if="action.owner" class="pm-card-detail">担当: {{ action.owner }}</p>
                </div>
              </div>
            </div>
          </div>

          <div v-if="activeSecondaryTab === 'evidence'" class="side-card evidence-panel">
            <div class="side-header">
              <h3>根拠ソース</h3>
            </div>
            <div v-if="reportEvidenceRefs.length" class="evidence-list">
              <div v-for="(ref, idx) in reportEvidenceRefs" :key="`${ref.source_id}-${idx}`" class="evidence-item">
                <strong>{{ ref.label }}</strong>
                <span class="evidence-meta">
                  {{ ref.source_type }} · {{ ref.char_start }}-{{ ref.char_end }}
                </span>
                <p>{{ ref.excerpt }}</p>
              </div>
            </div>
            <div v-else class="empty-state">根拠ソースはありません。</div>
          </div>

          <div v-if="activeSecondaryTab === 'raw'" class="side-card">
            <div class="side-header">
              <h3>Raw Data</h3>
            </div>
            <div class="society-section">
              <h4 class="society-section-title">Report JSON</h4>
              <pre class="society-raw-text">{{ reportJson }}</pre>
            </div>
            <div v-if="societyResult" class="society-section">
              <h4 class="society-section-title">Society Result</h4>
              <pre class="society-raw-text">{{ JSON.stringify(societyResult, null, 2) }}</pre>
            </div>
          </div>

          <div class="side-card chat-panel">
            <div class="side-header">
              <h3>Report Agent</h3>
            </div>
            <div class="chat-messages">
              <div v-if="followupAnswers.length === 0" class="chat-welcome">
                <div class="welcome-avatar">AI</div>
                <p>レポートについて質問できます。</p>
              </div>
              <template v-for="(qa, i) in followupAnswers" :key="i">
                <div class="chat-bubble user">
                  <div class="bubble-content">{{ qa.question }}</div>
                </div>
                <div class="chat-bubble agent">
                  <div class="bubble-avatar">AI</div>
                  <div v-if="qa.loading" class="bubble-content">
                    <div class="typing-indicator"><span></span><span></span><span></span></div>
                  </div>
                  <div v-else class="bubble-content">
                    {{ qa.answer }}
                    <div v-if="qa.evidenceRefs?.length" class="chat-evidence">
                      根拠: {{ qa.evidenceRefs.map((ref) => ref.label).join(', ') }}
                    </div>
                  </div>
                </div>
              </template>
            </div>
            <div class="chat-input-area">
              <input
                v-model="followupQuestion"
                type="text"
                placeholder="質問を入力..."
                @keyup.enter="handleFollowup"
                :disabled="isFollowupLoading"
                class="chat-input"
              />
              <button
                class="btn btn-primary chat-send"
                @click="handleFollowup"
                :disabled="!followupQuestion.trim() || isFollowupLoading"
              >
                &#8593;
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.results-page { display: flex; flex-direction: column; gap: var(--section-gap); }
.meta-report-panel { display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1rem; }
.meta-summary-grid,
.meta-cycle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.85rem;
}
.meta-cycle-card {
  padding: 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--bg-card) 88%, #16344b 12%);
}
.meta-cycle-head {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: center;
}
.meta-cycle-copy {
  margin-top: 0.55rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
}
.meta-stop-reason {
  font-size: 0.85rem;
  text-transform: capitalize;
}

.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 400px; gap: 1rem; color: var(--text-muted); }
.loading-dots { display: flex; gap: 4px; }
.loading-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: typing-dot 1.4s ease-in-out infinite; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
  padding: var(--panel-padding);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.result-header h2 { font-size: 1.1rem; font-weight: 700; }
.header-left {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.header-meta {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.header-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; justify-content: flex-end; }
.btn-ghost { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.5rem 1rem; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-secondary); font-family: var(--font-sans); font-size: 0.82rem; font-weight: 500; cursor: pointer; text-decoration: none; transition: all 0.2s; }
.btn-ghost:hover { border-color: rgba(255,255,255,0.12); color: var(--text-primary); }

.error-banner { padding: 0.75rem 1.25rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: var(--radius-sm); color: var(--danger); font-size: 0.85rem; }
.quality-banner { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; padding: 0.75rem 1.25rem; border-radius: var(--radius-sm); font-size: 0.82rem; border: 1px solid var(--border); }
.quality-banner strong { font-family: var(--font-mono); font-size: 0.74rem; text-transform: uppercase; }
.quality-meta { font-family: var(--font-mono); font-size: 0.7rem; opacity: 0.85; }
.quality-verified { background: rgba(34,197,94,0.08); color: var(--success); border-color: rgba(34,197,94,0.2); }
.quality-draft { background: rgba(245,158,11,0.08); color: #f59e0b; border-color: rgba(245,158,11,0.2); }
.quality-unsupported { background: rgba(239,68,68,0.08); color: var(--danger); border-color: rgba(239,68,68,0.2); }
.evidence-panel { display: flex; flex-direction: column; gap: 0.75rem; }
.evidence-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; }
.evidence-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; flex-direction: column; gap: 0.5rem; }
.evidence-card-top { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.evidence-label { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); }
.evidence-type { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; }
.evidence-excerpt { font-size: 0.78rem; line-height: 1.6; color: var(--text-secondary); }

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 11rem), 1fr));
  gap: 0.75rem;
}

.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); display: flex; flex-direction: column; gap: 0.25rem; }
.stat-label { font-size: 0.7rem; color: var(--text-muted); font-weight: 500; }
.stat-value { font-family: var(--font-mono); font-size: 1.3rem; font-weight: 700; color: var(--accent); }

.results-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(18rem, 22rem);
  gap: 1rem;
  align-items: start;
}

.results-workspace {
  align-items: stretch;
}

.results-main {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: clamp(1rem, 1vw + 0.8rem, 2rem) clamp(1rem, 2vw, 2.5rem);
  min-height: min(70vh, 32rem);
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.tab-panel { animation: fade-in 0.3s ease; }
.primary-panel { display: flex; flex-direction: column; gap: 1rem; }
.mt-section { margin-top: 2rem; }

.workspace-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(16rem, 0.9fr);
  gap: 1rem;
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background:
    linear-gradient(135deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01)),
    radial-gradient(circle at top left, rgba(79, 70, 229, 0.18), transparent 40%);
}

.workspace-copy {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.workspace-eyebrow {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.workspace-title {
  font-size: clamp(1.15rem, 1.5vw, 1.45rem);
  line-height: 1.2;
}

.workspace-description {
  font-size: 0.84rem;
  line-height: 1.6;
  color: var(--text-secondary);
}

.workspace-highlights {
  display: grid;
}

.workspace-highlight-card,
.workspace-inline-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: rgba(255,255,255,0.03);
  padding: 0.9rem 1rem;
}

.workspace-highlight-label {
  display: block;
  margin-bottom: 0.35rem;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  text-transform: uppercase;
  color: var(--text-muted);
}

.workspace-highlight-value {
  display: block;
  margin-bottom: 0.5rem;
  font-size: 1.35rem;
  color: var(--accent);
}

.workspace-highlight-card p,
.workspace-inline-copy {
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--text-secondary);
}

.workspace-inline-list {
  margin-top: 0.75rem;
  padding-left: 1.1rem;
  display: grid;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.report-panel { display: flex; flex-direction: column; gap: 1rem; }
.report-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.report-toolbar-note { font-size: 0.78rem; color: var(--text-muted); }
.report-copy-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.report-content { max-width: 720px; line-height: 1.85; font-size: 0.9rem; }
.report-content { user-select: text; -webkit-user-select: text; }
.report-content :deep(h2) { font-size: 1.25rem; font-weight: 700; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }
.report-content :deep(h3) { font-size: 1.05rem; font-weight: 600; margin: 1.5rem 0 0.75rem; }
.report-content :deep(h4) { font-size: 0.92rem; font-weight: 600; margin: 1rem 0 0.5rem; color: var(--text-secondary); }
.report-content :deep(li) { margin-left: 1.5rem; margin-bottom: 0.4rem; }
.report-content :deep(strong) { font-weight: 600; }
.report-content :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 2rem 0; }

.content-title { font-size: 0.9rem; font-weight: 600; margin-bottom: 1.25rem; }
.empty-state { text-align: center; padding: 3rem; color: var(--text-muted); font-size: 0.85rem; }

.graph-tab-layout { display: flex; flex-direction: column; gap: 1rem; }
.graph-snapshot-large {
  height: clamp(20rem, 40vw, 32rem);
  background: radial-gradient(ellipse at 30% 40%, #0d0d2b 0%, #060614 50%, #020208 100%);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(100,100,255,0.12);
}

.cognitive-subtabs { display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.5rem; }
.subtab-btn { padding: 0.4rem 0.8rem; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-muted); font-family: var(--font-sans); font-size: 0.75rem; cursor: pointer; transition: all 0.2s; }
.subtab-btn.active { background: var(--accent-subtle); color: var(--accent); border-color: var(--accent); }
.cognitive-content { margin-top: 0.5rem; }

.results-side { display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; }
.side-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }
.side-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; gap: 0.75rem; flex-wrap: wrap; }
.side-header h3 { font-size: 0.82rem; font-weight: 600; }
.secondary-switcher-buttons { display: flex; gap: 0.4rem; flex-wrap: wrap; }

.graph-snapshot {
  height: clamp(14rem, 26vw, 18rem);
  background: radial-gradient(ellipse at 30% 40%, #0d0d2b 0%, #060614 50%, #020208 100%);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(100,100,255,0.12);
  margin-bottom: 0.5rem;
}
.graph-error-note {
  margin-bottom: 0.75rem;
  padding: 0.75rem 0.9rem;
  border: 1px solid rgba(245,158,11,0.24);
  border-radius: var(--radius-sm);
  background: rgba(245,158,11,0.08);
  color: var(--text-secondary);
  font-size: 0.8rem;
  line-height: 1.6;
}

.chat-panel { display: flex; flex-direction: column; max-height: min(32rem, 70vh); }
.chat-messages { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 0.6rem; padding: 0.5rem 0; min-height: 80px; max-height: min(15rem, 35vh); }
.chat-welcome { display: flex; gap: 0.6rem; align-items: flex-start; padding: 0.75rem; background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); }
.chat-welcome p { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.5; }
.welcome-avatar, .bubble-avatar { width: 28px; height: 28px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--highlight)); display: flex; align-items: center; justify-content: center; font-family: var(--font-mono); font-size: 0.6rem; font-weight: 700; color: white; flex-shrink: 0; }
.chat-bubble { display: flex; gap: 0.5rem; animation: fade-in 0.3s ease; }
.chat-bubble.user { justify-content: flex-end; }
.chat-bubble.user .bubble-content { background: var(--accent); color: white; border-radius: var(--radius-sm) var(--radius-sm) 2px var(--radius-sm); padding: 0.6rem 0.85rem; font-size: 0.82rem; max-width: 85%; }
.chat-bubble.agent { align-items: flex-start; }
.chat-bubble.agent .bubble-content { background: rgba(255,255,255,0.04); border: 1px solid var(--border); border-radius: 2px var(--radius-sm) var(--radius-sm) var(--radius-sm); padding: 0.6rem 0.85rem; font-size: 0.82rem; line-height: 1.6; max-width: 85%; }
.chat-evidence { margin-top: 0.45rem; font-size: 0.72rem; color: var(--text-muted); }
.typing-indicator { display: flex; gap: 3px; padding: 0.2rem 0; }
.typing-indicator span { width: 5px; height: 5px; border-radius: 50%; background: var(--text-muted); animation: typing-dot 1.4s ease-in-out infinite; }
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
.chat-input-area { display: flex; gap: 0.5rem; margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border); }
.chat-input { flex: 1; padding: 0.55rem 0.85rem; background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-primary); font-family: var(--font-sans); font-size: 0.82rem; outline: none; }
.chat-input:focus { border-color: var(--accent); }
.evidence-meta { display: block; margin-top: 0.2rem; font-size: 0.68rem; color: var(--text-muted); font-family: var(--font-mono); }
.chat-input::placeholder { color: var(--text-muted); }
.chat-send { width: 36px; height: 36px; padding: 0; border-radius: 50%; font-size: 1rem; }
.evidence-list { display: flex; flex-direction: column; gap: 0.6rem; }
.evidence-item { padding: 0.7rem 0.8rem; border: 1px solid var(--border); border-radius: var(--radius-sm); background: rgba(255,255,255,0.02); }
.evidence-item strong { display: block; margin-bottom: 0.25rem; font-size: 0.78rem; }
.evidence-item p { font-size: 0.76rem; color: var(--text-secondary); line-height: 1.5; }

.pm-board-result { display: flex; flex-direction: column; gap: 1.5rem; }
.pm-section { }
.pm-section-title { font-size: 0.95rem; font-weight: 600; margin-bottom: 0.75rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--border); }
.pm-section-content { font-size: 1.1rem; font-weight: 500; line-height: 1.6; }
.pm-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem 1rem; margin-bottom: 0.5rem; }
.pm-card-header { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; margin-bottom: 0.3rem; }
.pm-card-label { font-size: 0.88rem; font-weight: 500; }
.pm-card-detail { font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.25rem; }
.pm-risk { color: var(--danger); }
.pm-confidence { font-family: var(--font-mono); font-size: 0.78rem; font-weight: 600; color: var(--accent); }
.pm-risk-badge { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; padding: 0.1rem 0.4rem; border-radius: 3px; text-transform: uppercase; }
.pm-risk-badge.risk-high { background: rgba(239,68,68,0.15); color: var(--danger); }
.pm-risk-badge.risk-medium { background: rgba(245,158,11,0.15); color: #f59e0b; }
.pm-risk-badge.risk-low { background: rgba(34,197,94,0.15); color: var(--success); }
.pm-highlight { border-color: var(--accent); background: rgba(99,102,241,0.05); }
.pm-highlight p { margin: 0.3rem 0; font-size: 0.88rem; }
.pm-scope-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.pm-timeline-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; }
.pm-period-label { font-family: var(--font-mono); font-size: 0.85rem; font-weight: 600; color: var(--accent); margin-bottom: 0.5rem; }
.pm-action { display: flex; flex-direction: column; gap: 0.2rem; }
.pm-action-header { display: flex; align-items: center; gap: 0.5rem; }
.pm-action-number { width: 24px; height: 24px; border-radius: 50%; background: var(--accent); color: white; display: flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 700; flex-shrink: 0; }
.pm-contradiction { border-left: 3px solid var(--danger); }
.pm-overall { display: flex; align-items: center; gap: 0.75rem; padding: 1rem; background: rgba(99,102,241,0.08); border-radius: var(--radius-sm); font-size: 0.9rem; font-weight: 500; }
.pm-overall-score { font-family: var(--font-mono); font-size: 1.5rem; font-weight: 700; color: var(--accent); }
.pm-player { font-size: 0.82rem; color: var(--text-secondary); padding-left: 0.5rem; margin: 0.2rem 0; }

@media (max-width: 1200px) {
  .results-layout {
    grid-template-columns: minmax(0, 1fr) minmax(17rem, 20rem);
  }
}

@media (max-width: 900px) {
  .results-layout {
    grid-template-columns: 1fr;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .result-header {
    gap: 0.75rem;
  }

  .header-actions {
    flex-direction: column;
  }

  .btn-ghost {
    width: 100%;
    justify-content: center;
  }

  .tab-btn {
    width: 100%;
    border-bottom: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .results-main {
    border-radius: var(--radius);
    min-height: auto;
  }

  .report-toolbar {
    align-items: stretch;
  }

  .report-copy-btn {
    width: 100%;
    justify-content: center;
  }

  .graph-snapshot {
    height: 14rem;
  }

  .chat-panel {
    max-height: none;
  }

  .chat-messages {
    max-height: 16rem;
  }

  .chat-input-area {
    flex-wrap: wrap;
  }

  .chat-input,
  .chat-send {
    width: 100%;
  }

  .chat-send {
    border-radius: var(--radius-sm);
    height: 40px;
  }
}

/* Society Sub-tabs */
.society-sub-tabs {
  display: flex;
  gap: 0.25rem;
  padding: 0.5rem 0;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--border-default, #333);
  overflow-x: auto;
}
.society-sub-tab {
  padding: 0.4rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted, #888);
  background: none;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}
.society-sub-tab:hover { color: var(--text-primary, #fff); background: rgba(255,255,255,0.05); }
.society-sub-tab.active {
  color: var(--accent, #6366f1);
  background: rgba(99,102,241,0.1);
}
.society-people-panel { height: 600px; display: flex; flex-direction: column; }
.society-raw-text {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-muted, #888);
  background: rgba(0,0,0,0.3);
  padding: 1rem;
  border-radius: 0.5rem;
  overflow: auto;
  max-height: 600px;
  white-space: pre-wrap;
  word-break: break-all;
}

/* Society Results */
.society-results { display: flex; flex-direction: column; gap: 1.5rem; }
.society-section { display: flex; flex-direction: column; gap: 0.75rem; }
.society-section-title { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
.society-stats-row { display: flex; gap: 1.5rem; flex-wrap: wrap; }
.society-stat { display: flex; flex-direction: column; gap: 0.15rem; }
.society-stat-label { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; }
.society-stat-value { font-family: var(--font-mono); font-size: 1.2rem; font-weight: 700; color: var(--text-primary); }
.society-distribution { display: flex; flex-direction: column; gap: 0.5rem; }
.society-bar-row { display: flex; align-items: center; gap: 0.75rem; }
.society-bar-label { width: 100px; font-size: 0.78rem; color: var(--text-secondary); text-align: right; flex-shrink: 0; }
.society-bar-track { flex: 1; height: 20px; background: rgba(255,255,255,0.05); border-radius: 3px; overflow: hidden; }
.society-bar-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.6s ease; }
.society-bar-value { width: 50px; font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-primary); font-weight: 600; }
.society-list { margin: 0; padding-left: 1.2rem; font-size: 0.82rem; color: var(--text-secondary); line-height: 1.8; }
.society-issue-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; }
.society-issue-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; flex-direction: column; gap: 0.45rem; }
.society-issue-top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.society-issue-label { font-size: 0.84rem; font-weight: 600; color: var(--text-primary); }
.society-issue-score { font-family: var(--font-mono); font-size: 0.72rem; color: var(--accent); }
.society-issue-desc { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.5; }
.society-issue-metrics { display: flex; flex-wrap: wrap; gap: 0.5rem; font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); }
.society-chip-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.society-chip { font-size: 0.76rem; padding: 0.28rem 0.58rem; border-radius: 999px; border: 1px solid rgba(99,102,241,0.24); background: rgba(99,102,241,0.08); color: var(--accent); }
.society-colony-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.9rem; display: flex; flex-direction: column; gap: 0.65rem; }
.society-colony-head { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.society-colony-title { font-size: 0.84rem; font-weight: 600; color: var(--text-primary); }
.society-colony-meta { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); }
.society-colony-report { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.65; white-space: pre-wrap; }
.society-colony-scenarios { display: grid; gap: 0.5rem; }
.society-intervention-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 0.75rem; }
.society-intervention-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; flex-direction: column; gap: 0.45rem; }
.society-intervention-top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.society-intervention-label { font-size: 0.84rem; font-weight: 600; color: var(--text-primary); }
.society-intervention-effect { font-family: var(--font-mono); font-size: 0.7rem; color: var(--accent); }
.society-intervention-effect.observed { color: var(--success); }
.society-intervention-effect.heuristic { color: var(--accent); }
.society-intervention-desc { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.55; }
.society-intervention-issues { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); }
.society-intervention-metrics { display: flex; flex-wrap: wrap; gap: 0.5rem; font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); }
.society-intervention-hint { font-family: var(--font-mono); font-size: 0.74rem; color: var(--accent); }
.society-evidence-list { display: grid; gap: 0.45rem; }
.society-evidence-card { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.6rem; background: rgba(255,255,255,0.02); }
.society-evidence-top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; font-size: 0.72rem; font-weight: 600; color: var(--text-primary); }
.society-evidence-card p { margin-top: 0.25rem; font-size: 0.76rem; color: var(--text-secondary); line-height: 1.5; }
.society-backtest-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin-bottom: 0.75rem; }
.society-backtest-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0.75rem; }
.society-backtest-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem; display: flex; flex-direction: column; gap: 0.45rem; }
.society-backtest-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem; }
.society-backtest-title { font-size: 0.84rem; font-weight: 600; color: var(--text-primary); }
.society-backtest-meta { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); margin-top: 0.15rem; }
.society-backtest-outcome { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.6; }
.society-backtest-match { display: flex; gap: 0.45rem; font-size: 0.76rem; color: var(--text-secondary); }
.society-backtest-label { font-family: var(--font-mono); color: var(--text-muted); min-width: 3.8rem; }
.society-verdict-badge { font-family: var(--font-mono); font-size: 0.68rem; padding: 0.18rem 0.45rem; border-radius: 999px; border: 1px solid var(--border); }
.society-verdict-badge.verdict-hit { color: var(--success); border-color: rgba(34,197,94,0.24); background: rgba(34,197,94,0.1); }
.society-verdict-badge.verdict-partial { color: #f59e0b; border-color: rgba(245,158,11,0.28); background: rgba(245,158,11,0.1); }
.society-verdict-badge.verdict-miss { color: var(--danger); border-color: rgba(239,68,68,0.24); background: rgba(239,68,68,0.1); }
.society-empty-copy { font-size: 0.8rem; color: var(--text-muted); line-height: 1.6; }
.society-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; }
.society-metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.75rem; text-align: center; display: flex; flex-direction: column; gap: 0.25rem; }
.society-metric-label { font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; }
.society-metric-score { font-family: var(--font-mono); font-size: 1.3rem; font-weight: 700; color: var(--accent); }
.society-meeting-summary { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.7; }
.society-participants-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.society-participant-chip { font-size: 0.78rem; padding: 0.3rem 0.6rem; border-radius: 999px; border: 1px solid var(--border); background: rgba(255,255,255,0.03); display: flex; align-items: center; gap: 0.35rem; }
.society-participant-chip.expert { border-color: rgba(99,102,241,0.3); color: var(--accent); }
.society-participant-chip.citizen_representative { border-color: rgba(34,197,94,0.3); color: var(--success); }
.participant-stance-tag { font-family: var(--font-mono); font-size: 0.65rem; color: var(--text-muted); }
.society-disagreement { margin-bottom: 0.5rem; }
.disagreement-topic { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.disagreement-positions { display: flex; flex-direction: column; gap: 0.2rem; margin-top: 0.25rem; }
.disagreement-pos { font-size: 0.78rem; color: var(--text-secondary); }
.society-scenario-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.75rem; margin-bottom: 0.5rem; }
.scenario-name { font-size: 0.85rem; font-weight: 600; margin-bottom: 0.25rem; }
.scenario-desc { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; }
.scenario-prob { font-family: var(--font-mono); font-size: 0.72rem; color: var(--accent); margin-top: 0.25rem; }
.society-shift { display: flex; align-items: center; gap: 0.75rem; font-size: 0.82rem; margin-bottom: 0.35rem; }
.shift-name { font-weight: 600; }
.shift-flow { font-family: var(--font-mono); color: var(--accent); }
.society-assessment { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.7; }

/* Decision Brief council section */
.brief-council-section { margin-top: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }
.brief-council-title { font-size: 0.85rem; font-weight: 600; margin-bottom: 0.5rem; }
.brief-council-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.brief-council-chip { font-size: 0.78rem; padding: 0.3rem 0.6rem; border-radius: 999px; border: 1px solid var(--border); background: rgba(255,255,255,0.03); display: flex; align-items: center; gap: 0.35rem; }
.brief-council-chip.expert { border-color: rgba(99,102,241,0.3); color: var(--accent); }
.brief-council-chip.devil_advocate { border-color: rgba(239,68,68,0.3); color: var(--danger); }
.brief-council-stance { font-family: var(--font-mono); font-size: 0.65rem; color: var(--text-muted); }
.brief-devil-advocate { padding: 0.85rem; border-left: 3px solid var(--danger); background: rgba(239,68,68,0.05); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.brief-devil-advocate p { font-size: 0.84rem; color: var(--text-secondary); line-height: 1.7; }

/* Transcript Tab */
.transcript-filters { display: flex; gap: 0.25rem; margin-bottom: 0.75rem; }
.transcript-loading { font-size: 0.8rem; color: var(--text-muted); padding: 1rem; text-align: center; }
.transcript-list { display: flex; flex-direction: column; gap: 0.5rem; max-height: 60vh; overflow-y: auto; }
.transcript-entry { padding: 0.6rem 0.75rem; border-left: 3px solid var(--border); background: rgba(255,255,255,0.02); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; transition: border-color 0.2s; }
.transcript-entry.transcript-stance-changed { border-left-color: var(--accent, #6366f1); }
.transcript-meta { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; flex-wrap: wrap; }
.transcript-name { font-size: 0.78rem; font-weight: 600; color: var(--text-primary); }
.transcript-phase-badge { font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 4px; background: rgba(255,255,255,0.06); color: var(--text-muted); font-family: var(--font-mono); }
.transcript-stance { font-size: 0.68rem; padding: 0.1rem 0.35rem; border-radius: 4px; border: 1px solid var(--border); color: var(--text-secondary); }
.transcript-text { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.6; white-space: pre-line; }
.transcript-address { font-size: 0.72rem; color: var(--text-muted); margin-top: 0.2rem; }
</style>
