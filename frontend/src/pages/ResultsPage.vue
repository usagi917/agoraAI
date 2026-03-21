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
} from '../api/client'
import { useForceGraph } from '../composables/useForceGraph'
import TemporalSlider from '../components/TemporalSlider.vue'
import ProbabilityChart from '../components/ProbabilityChart.vue'
import ScenarioCompare from '../components/ScenarioCompare.vue'
import SocietyTimeline from '../components/SocietyTimeline.vue'
import AgreementHeatmap from '../components/AgreementHeatmap.vue'
import AgentMindView from '../components/AgentMindView.vue'
import MemoryStreamViewer from '../components/MemoryStreamViewer.vue'
import EvaluationDashboard from '../components/EvaluationDashboard.vue'
import ToMMapVisualization from '../components/ToMMapVisualization.vue'
import SocialNetworkDynamics from '../components/SocialNetworkDynamics.vue'
import KnowledgeGraphExplorer from '../components/KnowledgeGraphExplorer.vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

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
const currentRound = ref(0)
const transitionTargetRound = ref<number | null>(null)
const transitionProgress = ref(0)
const isPlaying = ref(false)
const colonies = ref<ColonyResponse[]>([])
const cognitiveStore = useCognitiveStore()
const activeTab = ref<'report' | 'scenarios' | 'pm_evaluation' | 'graph' | 'society'>('report')
const isCognitiveMode = computed(() => cognitiveStore.cognitiveMode === 'advanced')
const cognitiveSubTab = ref<'mind' | 'memory' | 'evaluation' | 'tom' | 'social' | 'kg'>('mind')
let playbackFrame: number | null = null
let playbackStartedAt: number | null = null

const { setFullGraph } = useForceGraph(graphContainer)

// Follow-up
const followupQuestion = ref('')
const followupAnswers = ref<Array<{ question: string; answer: string; loading?: boolean; evidenceRefs?: EvidenceRef[] }>>([])
const isFollowupLoading = ref(false)
const copyState = ref<'idle' | 'success' | 'error'>('idle')
let copyStateTimer: number | null = null

const isPipelineMode = computed(() => sim.value?.mode === 'pipeline')
const isSocietyMode = computed(() => sim.value?.mode === 'society')
const societyResult = computed(() => sim.value?.metadata?.society_result || null)
const meetingReport = computed(() => societyResult.value?.meeting || null)
const hasScenarios = computed(() => (report.value?.scenarios?.length ?? 0) > 0)
const hasPmBoard = computed(() => {
  if (isPipelineMode.value) return !!report.value?.pm_board
  return sim.value?.mode === 'pm_board' && report.value?.sections
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
  if (report.value?.type === 'pm_board') return report.value as PMBoardReportResponse
  return null
})
const normalizedScenarios = computed(() => (
  ((report.value?.type === 'pipeline' || report.value?.type === 'swarm')
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
const agreementMatrix = computed(() => {
  if (!report.value?.agreement_matrix) return null
  return report.value.agreement_matrix as { colony_ids: string[]; matrix: number[][] }
})
const canCopyReport = computed(() => reportText.value.trim().length > 0)
const snapshotByRound = computed(() => new Map(graphSnapshots.value.map((snapshot) => [snapshot.round, snapshot])))
const sliderDisplayValue = computed(() => {
  if (transitionTargetRound.value === null) return currentRound.value
  return currentRound.value + transitionProgress.value
})

const totalRounds = computed(() => {
  if (graphSnapshots.value.length === 0) return 0
  return graphSnapshots.value[graphSnapshots.value.length - 1].round
})

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

  if (rawProgress < 1) {
    playbackFrame = requestAnimationFrame(stepPlayback)
    return
  }

  currentRound.value = transitionTargetRound.value
  resetTransitionState()

  if (currentRound.value < totalRounds.value) {
    queueNextTransition(currentRound.value)
    return
  }

  isPlaying.value = false
}

function beginRoundTransition(fromRound: number) {
  const toSnapshot = snapshotByRound.value.get(fromRound + 1)
  if (!toSnapshot) {
    stopPlayback(fromRound)
    return
  }

  stopPlaybackLoop()
  currentRound.value = fromRound
  transitionTargetRound.value = toSnapshot.round
  transitionProgress.value = 0
  setFullGraph(toSnapshot.nodes, toSnapshot.edges)
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

    // デフォルトタブ設定
    if (isSocietyMode.value) {
      activeTab.value = 'society'
    } else if (isPipelineMode.value) {
      activeTab.value = 'report'
    } else if (sim.value.mode === 'pm_board') {
      activeTab.value = 'pm_evaluation'
    } else if (sim.value.mode === 'swarm' || sim.value.mode === 'hybrid') {
      activeTab.value = 'scenarios'
    }

    // Colony データ取得
    if (hasScenarios.value || sim.value.swarm_id) {
      colonies.value = await getSimulationColonies(simId).catch(() => [])
    }

    // 最新グラフ表示
    if (graphHistory.length > 0) {
      const latest = graphHistory[graphHistory.length - 1]
      currentRound.value = latest.round
      await nextTick()
      setFullGraph(latest.nodes, latest.edges)
    } else {
      const graphData = await getSimulationGraph(simId).catch(() => null)
      if (graphData?.nodes?.length) {
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

      <!-- Tabs: 4タブ構成 -->
      <div class="tab-bar">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'report' }"
          @click="activeTab = 'report'"
        >
          統合レポート
        </button>
        <button
          v-if="hasScenarios"
          class="tab-btn"
          :class="{ active: activeTab === 'scenarios' }"
          @click="activeTab = 'scenarios'"
        >
          シナリオ分析
        </button>
        <button
          v-if="hasPmBoard"
          class="tab-btn"
          :class="{ active: activeTab === 'pm_evaluation' }"
          @click="activeTab = 'pm_evaluation'"
        >
          PM評価
        </button>
        <button
          v-if="isSocietyMode"
          class="tab-btn"
          :class="{ active: activeTab === 'society' }"
          @click="activeTab = 'society'"
        >
          Society 分析
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'graph' }"
          @click="activeTab = 'graph'"
        >
          ナレッジグラフ
        </button>
      </div>

      <div class="results-layout">
        <!-- Left: Main Content -->
        <div class="results-main">
          <!-- Society tab -->
          <div v-if="activeTab === 'society' && societyResult" class="tab-panel">
            <div class="society-results">
              <div class="society-section">
                <h4 class="society-section-title">意見分布</h4>
                <div class="society-stats-row">
                  <span class="society-stat">
                    <span class="society-stat-label">人口</span>
                    <span class="society-stat-value">{{ societyResult.population_count?.toLocaleString() }}</span>
                  </span>
                  <span class="society-stat">
                    <span class="society-stat-label">選抜</span>
                    <span class="society-stat-value">{{ societyResult.selected_count }}</span>
                  </span>
                  <span class="society-stat">
                    <span class="society-stat-label">平均信頼度</span>
                    <span class="society-stat-value">{{ ((societyResult.aggregation?.average_confidence || 0) * 100).toFixed(1) }}%</span>
                  </span>
                </div>
                <div v-if="societyResult.aggregation?.stance_distribution" class="society-distribution">
                  <div
                    v-for="(ratio, stance) in societyResult.aggregation.stance_distribution"
                    :key="stance"
                    class="society-bar-row"
                  >
                    <span class="society-bar-label">{{ stance }}</span>
                    <div class="society-bar-track">
                      <div class="society-bar-fill" :style="{ width: (Number(ratio) * 100) + '%' }" />
                    </div>
                    <span class="society-bar-value">{{ (Number(ratio) * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
              <div v-if="societyResult.aggregation?.top_concerns?.length" class="society-section">
                <h4 class="society-section-title">主要な懸念事項</h4>
                <ul class="society-list">
                  <li v-for="concern in societyResult.aggregation.top_concerns" :key="concern">{{ concern }}</li>
                </ul>
              </div>
              <div v-if="societyResult.aggregation?.top_priorities?.length" class="society-section">
                <h4 class="society-section-title">主要な優先事項</h4>
                <ul class="society-list">
                  <li v-for="priority in societyResult.aggregation.top_priorities" :key="priority">{{ priority }}</li>
                </ul>
              </div>
              <div v-if="societyResult.evaluation" class="society-section">
                <h4 class="society-section-title">評価メトリクス</h4>
                <div class="society-metrics">
                  <div v-for="(score, metric) in societyResult.evaluation" :key="metric" class="society-metric-card">
                    <span class="society-metric-label">{{ metric }}</span>
                    <span class="society-metric-score">{{ (Number(score) * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
              <template v-if="meetingReport">
                <div class="society-section">
                  <h4 class="society-section-title">Meeting Layer: 構造化議論</h4>
                  <p class="society-meeting-summary">{{ meetingReport.summary }}</p>
                </div>
                <div v-if="meetingReport.participants?.length" class="society-section">
                  <h4 class="society-section-title">参加者</h4>
                  <div class="society-participants-grid">
                    <div v-for="(p, i) in meetingReport.participants" :key="i" class="society-participant-chip" :class="p.role">
                      {{ p.display_name || p.expertise || '参加者' }}
                      <span v-if="p.stance" class="participant-stance-tag">{{ p.stance }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="meetingReport.consensus_points?.length" class="society-section">
                  <h4 class="society-section-title">合意点</h4>
                  <ul class="society-list">
                    <li v-for="point in meetingReport.consensus_points" :key="point">{{ point }}</li>
                  </ul>
                </div>
                <div v-if="meetingReport.disagreement_points?.length" class="society-section">
                  <h4 class="society-section-title">対立点</h4>
                  <div v-for="(dp, i) in meetingReport.disagreement_points" :key="i" class="society-disagreement">
                    <span class="disagreement-topic">{{ dp.topic }}</span>
                    <div v-if="dp.positions" class="disagreement-positions">
                      <span v-for="pos in dp.positions" :key="pos.participant" class="disagreement-pos">
                        {{ pos.participant }}: {{ pos.position }}
                      </span>
                    </div>
                  </div>
                </div>
                <div v-if="meetingReport.scenarios?.length" class="society-section">
                  <h4 class="society-section-title">シナリオ</h4>
                  <div v-for="(sc, i) in meetingReport.scenarios" :key="i" class="society-scenario-card">
                    <div class="scenario-name">{{ sc.name }}</div>
                    <div class="scenario-desc">{{ sc.description }}</div>
                    <div v-if="sc.probability" class="scenario-prob">確率: {{ (sc.probability * 100).toFixed(0) }}%</div>
                  </div>
                </div>
                <div v-if="meetingReport.stance_shifts?.length" class="society-section">
                  <h4 class="society-section-title">スタンス変化</h4>
                  <div v-for="(shift, i) in meetingReport.stance_shifts" :key="i" class="society-shift">
                    <span class="shift-name">{{ shift.participant }}</span>
                    <span class="shift-flow">{{ shift.initial_position || shift.from }} &rarr; {{ shift.final_position || shift.to }}</span>
                  </div>
                </div>
                <div v-if="meetingReport.recommendations?.length" class="society-section">
                  <h4 class="society-section-title">提言</h4>
                  <ul class="society-list">
                    <li v-for="rec in meetingReport.recommendations" :key="rec">{{ rec }}</li>
                  </ul>
                </div>
                <div v-if="meetingReport.overall_assessment" class="society-section">
                  <h4 class="society-section-title">総合評価</h4>
                  <p class="society-assessment">{{ meetingReport.overall_assessment }}</p>
                </div>
              </template>
              <div class="society-section">
                <h4 class="society-section-title">Society シミュレーション履歴</h4>
                <SocietyTimeline
                  :current-sim-id="simId"
                  :population-id="societyResult?.population_id"
                />
              </div>
            </div>
          </div>

          <!-- Report tab -->
          <div v-if="activeTab === 'report'" class="tab-panel">
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

          <!-- Scenarios tab -->
          <div v-if="activeTab === 'scenarios' && report?.scenarios" class="tab-panel">
            <ScenarioCompare :scenarios="normalizedScenarios" />

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
          </div>

          <!-- PM Evaluation tab -->
          <div v-if="activeTab === 'pm_evaluation' && pmBoardData" class="tab-panel">
            <div class="pm-board-result">
              <template v-if="pmBoardData.sections">
                <div v-if="pmBoardData.sections.core_question" class="pm-section">
                  <h3 class="pm-section-title">1. 核心質問</h3>
                  <p class="pm-section-content">{{ pmBoardData.sections.core_question }}</p>
                </div>

                <div v-if="pmBoardData.sections.assumptions?.length" class="pm-section">
                  <h3 class="pm-section-title">2. 前提条件</h3>
                  <div v-for="(a, i) in pmBoardData.sections.assumptions" :key="i" class="pm-card">
                    <div class="pm-card-header">
                      <span class="pm-card-label">{{ a.assumption }}</span>
                      <span class="pm-confidence" :style="{ color: a.confidence > 0.7 ? 'var(--success)' : a.confidence > 0.4 ? 'var(--warning, #f59e0b)' : 'var(--danger)' }">
                        {{ (a.confidence * 100).toFixed(0) }}%
                      </span>
                    </div>
                    <p v-if="a.evidence" class="pm-card-detail">根拠: {{ a.evidence }}</p>
                    <p v-if="a.impact_if_wrong" class="pm-card-detail pm-risk">誤りの影響: {{ a.impact_if_wrong }}</p>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.uncertainties?.length" class="pm-section">
                  <h3 class="pm-section-title">3. 不確実性</h3>
                  <div v-for="(u, i) in pmBoardData.sections.uncertainties" :key="i" class="pm-card">
                    <div class="pm-card-header">
                      <span class="pm-card-label">{{ u.uncertainty }}</span>
                      <span class="pm-risk-badge" :class="'risk-' + u.risk_level">{{ u.risk_level }}</span>
                    </div>
                    <p v-if="u.validation_method" class="pm-card-detail">検証方法: {{ u.validation_method }}</p>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.risks?.length" class="pm-section">
                  <h3 class="pm-section-title">4. リスク</h3>
                  <div v-for="(r, i) in pmBoardData.sections.risks" :key="i" class="pm-card">
                    <div class="pm-card-header">
                      <span class="pm-card-label">{{ r.risk }}</span>
                      <span class="pm-confidence">{{ (r.probability * 100).toFixed(0) }}%</span>
                    </div>
                    <p v-if="r.mitigation" class="pm-card-detail">緩和策: {{ r.mitigation }}</p>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.winning_hypothesis?.if_true" class="pm-section">
                  <h3 class="pm-section-title">5. 勝利仮説</h3>
                  <div class="pm-card pm-highlight">
                    <p><strong>IF</strong> {{ pmBoardData.sections.winning_hypothesis.if_true }}</p>
                    <p><strong>THEN</strong> {{ pmBoardData.sections.winning_hypothesis.then_do }}</p>
                    <p><strong>TO ACHIEVE</strong> {{ pmBoardData.sections.winning_hypothesis.to_achieve }}</p>
                    <span class="pm-confidence">
                      確信度: {{ ((pmBoardData.sections.winning_hypothesis.confidence || 0) * 100).toFixed(0) }}%
                    </span>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.customer_validation_plan?.key_questions?.length" class="pm-section">
                  <h3 class="pm-section-title">6. 顧客検証計画</h3>
                  <div class="pm-card">
                    <p v-if="pmBoardData.sections.customer_validation_plan.target_segments?.length">
                      <strong>ターゲット:</strong> {{ pmBoardData.sections.customer_validation_plan.target_segments.join(', ') }}
                    </p>
                    <ul>
                      <li v-for="(q, i) in pmBoardData.sections.customer_validation_plan.key_questions" :key="i">{{ q }}</li>
                    </ul>
                    <p v-if="pmBoardData.sections.customer_validation_plan.success_criteria">
                      <strong>成功基準:</strong> {{ pmBoardData.sections.customer_validation_plan.success_criteria }}
                    </p>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.market_view?.market_size" class="pm-section">
                  <h3 class="pm-section-title">7. 市場/競合ビュー</h3>
                  <div class="pm-card">
                    <p><strong>市場規模:</strong> {{ pmBoardData.sections.market_view.market_size }}</p>
                    <p v-if="pmBoardData.sections.market_view.growth_rate"><strong>成長率:</strong> {{ pmBoardData.sections.market_view.growth_rate }}</p>
                    <div v-if="pmBoardData.sections.market_view.key_players?.length">
                      <strong>主要プレイヤー:</strong>
                      <div v-for="(p, i) in pmBoardData.sections.market_view.key_players" :key="i" class="pm-player">
                        {{ p.name }} — {{ p.position }}
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.gtm_hypothesis?.value_proposition" class="pm-section">
                  <h3 class="pm-section-title">8. GTM仮説</h3>
                  <div class="pm-card">
                    <p><strong>ターゲット:</strong> {{ pmBoardData.sections.gtm_hypothesis.target_customer }}</p>
                    <p><strong>価値提案:</strong> {{ pmBoardData.sections.gtm_hypothesis.value_proposition }}</p>
                    <p v-if="pmBoardData.sections.gtm_hypothesis.channel"><strong>チャネル:</strong> {{ pmBoardData.sections.gtm_hypothesis.channel }}</p>
                    <p v-if="pmBoardData.sections.gtm_hypothesis.pricing_model"><strong>価格モデル:</strong> {{ pmBoardData.sections.gtm_hypothesis.pricing_model }}</p>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.mvp_scope?.in_scope?.length" class="pm-section">
                  <h3 class="pm-section-title">9. MVPスコープ</h3>
                  <div class="pm-card">
                    <div class="pm-scope-columns">
                      <div>
                        <strong>In Scope:</strong>
                        <ul><li v-for="(s, i) in pmBoardData.sections.mvp_scope.in_scope" :key="i">{{ s }}</li></ul>
                      </div>
                      <div>
                        <strong>Out of Scope:</strong>
                        <ul><li v-for="(s, i) in pmBoardData.sections.mvp_scope.out_of_scope" :key="i">{{ s }}</li></ul>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.plan_30_60_90?.day_30" class="pm-section">
                  <h3 class="pm-section-title">10. 30/60/90日計画</h3>
                  <div class="pm-timeline-grid">
                    <div v-for="period in ['day_30', 'day_60', 'day_90']" :key="period" class="pm-card">
                      <h4 class="pm-period-label">{{ period === 'day_30' ? '30日' : period === 'day_60' ? '60日' : '90日' }}</h4>
                      <div v-if="pmBoardData.sections.plan_30_60_90[period]?.goals?.length">
                        <strong>目標:</strong>
                        <ul><li v-for="(g, i) in pmBoardData.sections.plan_30_60_90[period].goals" :key="i">{{ g }}</li></ul>
                      </div>
                      <div v-if="pmBoardData.sections.plan_30_60_90[period]?.actions?.length">
                        <strong>アクション:</strong>
                        <ul><li v-for="(a, i) in pmBoardData.sections.plan_30_60_90[period].actions" :key="i">{{ a }}</li></ul>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="pmBoardData.sections.top_5_actions?.length" class="pm-section">
                  <h3 class="pm-section-title">11. 今すぐやるべき5アクション</h3>
                  <div v-for="(action, idx) in pmBoardData.sections.top_5_actions" :key="idx" class="pm-card pm-action">
                    <div class="pm-action-header">
                      <span class="pm-action-number">{{ Number(idx) + 1 }}</span>
                      <span class="pm-card-label">{{ action.action }}</span>
                      <span v-if="action.confidence" class="pm-confidence">{{ (action.confidence * 100).toFixed(0) }}%</span>
                    </div>
                    <p v-if="action.owner" class="pm-card-detail">担当: {{ action.owner }}</p>
                    <p v-if="action.deadline" class="pm-card-detail">期限: {{ action.deadline }}</p>
                    <p v-if="action.evidence" class="pm-card-detail">根拠: {{ action.evidence }}</p>
                  </div>
                </div>
              </template>

              <div v-if="pmBoardData.contradictions?.length" class="pm-section">
                <h3 class="pm-section-title">矛盾検出</h3>
                <div v-for="(c, i) in pmBoardData.contradictions" :key="i" class="pm-card pm-contradiction">
                  <p><strong>{{ c.between?.join(' vs ') }}:</strong> {{ c.issue }}</p>
                  <p class="pm-card-detail">解決案: {{ c.resolution }}</p>
                </div>
              </div>

              <div v-if="pmBoardData.overall_confidence" class="pm-overall">
                <span>総合確信度:</span>
                <span class="pm-overall-score">{{ (pmBoardData.overall_confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>

          <!-- Graph tab -->
          <div v-if="activeTab === 'graph'" class="tab-panel">
            <div class="graph-tab-layout">
              <div ref="graphContainer" class="graph-snapshot-large"></div>
              <TemporalSlider
                v-if="graphSnapshots.length > 1"
                :total-rounds="totalRounds"
                :model-value="currentRound"
                :display-value="sliderDisplayValue"
                :playing="isPlaying"
                @update:model-value="onRoundChange"
                @update:playing="onPlayingChange"
              />

              <!-- Cognitive sub-tabs (quality profile) -->
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
                <KnowledgeGraphExplorer v-if="cognitiveSubTab === 'kg'" :entities="[]" :relations="[]" :communities="[]" />
              </div>
            </div>
          </div>
        </div>

        <!-- Right: Side Panel -->
        <div class="results-side">
          <!-- 3D Graph (when not in graph tab) -->
          <div v-if="activeTab !== 'graph'" class="side-card">
            <div class="side-header">
              <h3>3D Graph</h3>
            </div>
            <div ref="graphContainer" class="graph-snapshot"></div>
            <TemporalSlider
              v-if="graphSnapshots.length > 1"
              :total-rounds="totalRounds"
              :model-value="currentRound"
              :display-value="sliderDisplayValue"
              :playing="isPlaying"
              @update:model-value="onRoundChange"
              @update:playing="onPlayingChange"
            />
          </div>

          <!-- Followup Chat -->
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

          <div v-if="reportEvidenceRefs.length" class="side-card evidence-panel">
            <div class="side-header">
              <h3>根拠ソース</h3>
            </div>
            <div class="evidence-list">
              <div v-for="(ref, idx) in reportEvidenceRefs" :key="`${ref.source_id}-${idx}`" class="evidence-item">
                <strong>{{ ref.label }}</strong>
                <span class="evidence-meta">
                  {{ ref.source_type }} · {{ ref.char_start }}-{{ ref.char_end }}
                </span>
                <p>{{ ref.excerpt }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.results-page { display: flex; flex-direction: column; gap: var(--section-gap); }

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

.tab-bar { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.tab-btn { padding: 0.6rem 1.2rem; background: transparent; border: 1px solid var(--border); border-bottom: none; border-radius: var(--radius-sm) var(--radius-sm) 0 0; color: var(--text-muted); font-family: var(--font-sans); font-size: 0.82rem; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.tab-btn.active { background: var(--bg-card); color: var(--accent); }

.results-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(18rem, 22rem);
  gap: 1rem;
  align-items: start;
}

.results-main {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0 var(--radius) var(--radius) var(--radius);
  padding: clamp(1rem, 1vw + 0.8rem, 2rem) clamp(1rem, 2vw, 2.5rem);
  min-height: min(70vh, 32rem);
  min-width: 0;
}

.tab-panel { animation: fade-in 0.3s ease; }
.mt-section { margin-top: 2rem; }

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

.graph-snapshot {
  height: clamp(14rem, 26vw, 18rem);
  background: radial-gradient(ellipse at 30% 40%, #0d0d2b 0%, #060614 50%, #020208 100%);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(100,100,255,0.12);
  margin-bottom: 0.5rem;
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
</style>
