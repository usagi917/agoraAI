<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getSimulation,
  getSimulationColonies,
  getSimulationGraph,
  getSimulationTimeline,
  type ColonyResponse,
  type SimulationResponse,
  type SimulationTimelineEvent,
} from '../api/client'
import {
  useSimulationStore,
  type ColonyState,
  type SimulationStoreSnapshot,
} from '../stores/simulationStore'
import { useSimulationSSE } from '../composables/useSimulationSSE'
import { useGraphStore, type GraphStoreSnapshot } from '../stores/graphStore'
import { useActivityStore, type ActivityEntry } from '../stores/activityStore'
import { useForceGraph } from '../composables/useForceGraph'
import type { ThinkingVisualMode } from '../composables/useThinkingParticles'
import SimulationProgress from '../components/SimulationProgress.vue'
import ColonyGrid from '../components/ColonyGrid.vue'
import ActivityFeed from '../components/ActivityFeed.vue'
import SocietyProgress from '../components/SocietyProgress.vue'
import OpinionDistribution from '../components/OpinionDistribution.vue'
import LiveSocietyGraph from '../components/LiveSocietyGraph.vue'
import { useSocietyGraphStore } from '../stores/societyGraphStore'

const LIVE_SESSION_VERSION = 1

interface PersistedSimulationLiveState {
  version: number
  savedAt: number
  store: SimulationStoreSnapshot
  graph: GraphStoreSnapshot
  activity: ActivityEntry[]
}

const route = useRoute()
const router = useRouter()
const simId = route.params.id as string

const sim = ref<SimulationResponse | null>(null)
const graphCanvas = ref<HTMLElement | null>(null)
const selectedEntity = ref<any>(null)
const elapsedTime = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let persistTimer: ReturnType<typeof setTimeout> | null = null

const store = useSimulationStore()
const graphStore = useGraphStore()
const activityStore = useActivityStore()
const societyGraphStore = useSocietyGraphStore()
const sse = useSimulationSSE(simId)

const entityTypeColors: Record<string, string> = {
  organization: '#4FC3F7',
  person: '#FFB74D',
  policy: '#81C784',
  market: '#E57373',
  technology: '#BA68C8',
  resource: '#4DB6AC',
}

const showColonyGrid = computed(() => {
  if (store.isPipelineMode) {
    return store.pipelineStage === 'swarm' && store.colonies.length > 0
  }
  return (store.mode === 'swarm' || store.mode === 'hybrid' || store.mode === 'society_first') && store.colonies.length > 0
})

const thinkingMode = computed<ThinkingVisualMode>(() => {
  if (store.isSocietyMode) return 'society'
  if (store.phase === 'graphrag') return 'graphrag'
  if (store.phase === 'report' || store.status === 'generating_report') return 'report'
  if (showColonyGrid.value || store.pipelineStage === 'swarm') return 'swarm'
  if (store.status === 'running' || store.phase === 'world_building' || store.phase === 'simulation') {
    return 'simulation'
  }
  return 'idle'
})

const {
  graph,
  graphError,
  setFullGraph,
  applyDiff: applyGraphDiff,
  resetCamera,
} = useForceGraph(graphCanvas, thinkingMode)

const stageLabel = computed(() => {
  if (store.isSocietyMode) {
    if (store.isUnifiedMode) {
      switch (store.unifiedPhase) {
        case 'society_pulse': return '社会の脈動を測定中'
        case 'council': return `評議会 Round ${societyGraphStore.currentRound}`
        case 'synthesis': return '統合分析中'
        case 'completed': return '完了'
        default: return '準備中...'
      }
    }
    if (store.mode === 'society_first') {
      if (store.phase === 'issue_mining') return '重要論点を抽出中'
      if (store.phase === 'colony_execution') return 'Issue Colony 深掘り中'
      if (store.phase === 'aggregation') return 'Issue Colony 集約中'
      if (store.phase === 'report') return 'Society First レポート生成中'
    }
    switch (store.societyPhase) {
      case 'population': return '人口生成中'
      case 'selection': return 'エージェント選抜中'
      case 'activation': return '活性化レイヤー実行中'
      case 'evaluation': return '評価中'
      case 'completed': return '完了'
      default: return '準備中...'
    }
  }
  if (store.phase === 'graphrag') return 'GraphRAG 構築中'
  if (store.phase === 'verification') return '検証中'
  if (store.phase === 'report' || store.status === 'generating_report') return 'レポート生成中'
  if (store.isPipelineMode) {
    switch (store.pipelineStage) {
      case 'single': return 'Stage 1: 因果推論'
      case 'swarm': return 'Stage 2: 多視点検証'
      case 'pm_board': return 'Stage 3: PM評価'
      case 'completed': return '完了'
      default: return '準備中...'
    }
  }
  const phase = store.phase
  if (phase.startsWith('pm_analyzing_')) return `${phase.replace('pm_analyzing_', '')} 分析中...`
  if (phase === 'pm_synthesizing') return 'チーフPM 統合中...'
  if (phase === 'completed') return '完了'
  return store.phase
})

const formattedTime = computed(() => {
  const m = Math.floor(elapsedTime.value / 60)
  const s = elapsedTime.value % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
})

const phaseOverlay = computed(() => {
  const s = store.status
  if (s !== 'running' && s !== 'generating_report' && s !== 'connecting') return null
  const phase = store.phase
  const stage = store.pipelineStage
  if (phase === 'completed') return null

  if (phase === 'graphrag') return { icon: '◈', label: 'GraphRAG 構築中...' }
  if (phase === 'world_building') return { icon: '◇', label: '世界モデル構築中...' }
  if (phase === 'verification') return { icon: '◌', label: '出力を検証中...' }
  if (phase === 'simulation' && store.totalRounds > 0) {
    return { icon: '⟳', label: `Round ${store.currentRound}/${store.totalRounds} 推論中...` }
  }
  if (store.mode === 'society_first' && store.colonies.length > 0 && (phase === 'colony_execution' || phase === 'aggregation')) {
    return { icon: '⬡', label: `Issue Colony ${store.completedColonies}/${store.colonies.length} 実行中` }
  }
  if (stage === 'swarm' && store.colonies.length > 0) {
    return { icon: '⬡', label: `Colony ${store.completedColonies}/${store.colonies.length} 実行中` }
  }
  if (phase.startsWith('pm_analyzing_')) {
    const persona = phase.replace('pm_analyzing_', '')
    return { icon: '◉', label: `${persona} 分析中...` }
  }
  if (phase === 'pm_synthesizing') return { icon: '◉', label: 'チーフPM 統合中...' }
  if (phase === 'pm_analyzing') return { icon: '◉', label: 'PM Board 分析中...' }
  if (phase === 'report' || s === 'generating_report') return { icon: '▣', label: 'レポート生成中...' }
  if (stage === 'single') return { icon: '◈', label: '因果推論 実行中...' }
  if (stage === 'swarm') return { icon: '⬡', label: 'Swarm 実行中...' }
  if (stage === 'pm_board') return { icon: '◉', label: 'PM Board 実行中...' }

  return { icon: '◈', label: '処理中...' }
})

const emptyState = computed(() => {
  if (store.isSocietyMode) {
    if (store.isUnifiedMode) {
      switch (store.unifiedPhase) {
        case 'society_pulse':
          return {
            eyebrow: 'Society Pulse',
            title: '1,000人の社会反応を測定しています',
            detail: '人口統計・性格・価値観をサンプリングし、テーマに対する意見を収集中です。',
          }
        case 'council':
          return {
            eyebrow: 'Council Deliberation',
            title: '10人の評議会が議論しています',
            detail: '名前付きの代表者と専門家が3ラウンドの構造化議論を行っています。',
          }
        case 'synthesis':
          return {
            eyebrow: 'Synthesis',
            title: 'Decision Brief を生成しています',
            detail: '社会反応と評議会議論を統合し、意思決定に直結するレポートを作成中です。',
          }
        default:
          return {
            eyebrow: 'Unified Simulation',
            title: '統合シミュレーションを準備しています',
            detail: '社会の脈動 → 評議会 → Decision Brief の3フェーズで分析します。',
          }
      }
    }
    const currentPhase = store.phase
    if (store.mode === 'society_first') {
      if (currentPhase === 'issue_mining') {
        return {
          eyebrow: 'Issue Mining',
          title: '社会反応から重要論点を抽出しています',
          detail: '懸念・優先事項・理由を集約し、深掘り対象の Issue Colony を選んでいます。',
        }
      }
      if (currentPhase === 'colony_execution' || showColonyGrid.value) {
        return {
          eyebrow: 'Issue Colonies',
          title: '選抜された論点を深掘りしています',
          detail: '価格・規制・信頼などの重要論点ごとに colony を走らせ、市場シナリオを比較中です。',
        }
      }
    }
    const phase = store.societyPhase
    if (phase === 'population') {
      return {
        eyebrow: 'Population Generation',
        title: '1,000人のデジタル住民を生成しています',
        detail: '人口統計・性格・価値観を統計的にサンプリングし、社会ネットワークを構築中です。',
      }
    }
    if (phase === 'selection') {
      return {
        eyebrow: 'Agent Selection',
        title: 'テーマに関連する住民を選抜しています',
        detail: 'ショック感応度と属性多様性に基づく層化抽出を実行中です。',
      }
    }
    if (phase === 'activation') {
      return {
        eyebrow: 'Activation Layer',
        title: '選抜された住民が意見を表明しています',
        detail: '複数のLLMプロバイダを使って、各住民の立場・信頼度・理由を収集中です。',
      }
    }
    if (phase === 'evaluation') {
      return {
        eyebrow: 'Evaluation',
        title: 'シミュレーション品質を評価しています',
        detail: '意見多様性・整合性・キャリブレーションスコアを計算中です。',
      }
    }
    if (phase === 'meeting') {
      return {
        eyebrow: 'Meeting Layer',
        title: '代表者と専門家が議論しています',
        detail: '市民代表と専門家パネルによる構造化議論を実行中です。',
      }
    }
    return {
      eyebrow: 'Society Simulation',
      title: '社会シミュレーションを準備しています',
      detail: 'デジタル社会の初期化を進めています。',
    }
  }
  if (store.phase === 'graphrag') {
    return {
      eyebrow: 'Knowledge Extraction',
      title: 'GraphRAG が関係性を抽出しています',
      detail: '文書とプロンプトからエンティティとリンクを組み立てています。',
    }
  }
  if (store.phase === 'verification') {
    return {
      eyebrow: 'Verification',
      title: '生成結果を検証しています',
      detail: 'セクション欠落、根拠不足、出力契約違反を独立フェーズで確認中です。',
    }
  }
  if (store.phase === 'report' || store.status === 'generating_report') {
    return {
      eyebrow: 'Report Workflow',
      title: 'レポート骨子を組み立てています',
      detail: 'セクション単位で要約と統合を進めています。',
    }
  }
  if (showColonyGrid.value || store.pipelineStage === 'swarm') {
    return {
      eyebrow: 'Swarm Execution',
      title: '複数 Colony が仮説を検証しています',
      detail: '視点ごとのイベントと合意差分を集約中です。',
    }
  }
  return {
    eyebrow: 'Simulation Live',
    title: '世界モデルの初期状態を構築しています',
    detail: '最初のノードが現れるとグラフをそのまま追跡できます。',
  }
})

const graphContainerClass = computed(() => `tone-${thinkingMode.value}`)

function liveStateKey(id: string) {
  return `agent-ai:live:${id}`
}

function parseServerDate(value?: string | null) {
  if (!value) return null
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`
  const timestamp = Date.parse(normalized)
  return Number.isFinite(timestamp) ? timestamp : null
}

function stopElapsedTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function startElapsedTimer(startedAt?: string | null) {
  stopElapsedTimer()
  const startedMs = parseServerDate(startedAt) ?? Date.now()
  const update = () => {
    elapsedTime.value = Math.max(0, Math.floor((Date.now() - startedMs) / 1000))
  }
  update()
  if (store.status !== 'completed' && store.status !== 'failed') {
    timer = setInterval(update, 1000)
  }
}

function mapColonyResponse(colony: ColonyResponse): ColonyState {
  return {
    id: colony.id,
    colonyIndex: colony.colony_index,
    perspectiveId: colony.perspective_id,
    perspectiveLabel: colony.perspective_label,
    temperature: colony.temperature,
    adversarial: colony.adversarial,
    status: colony.status,
    currentRound: colony.current_round,
    totalRounds: colony.total_rounds,
    eventCount: 0,
  }
}

function timelineToEntries(events: SimulationTimelineEvent[]): ActivityEntry[] {
  return events.map((event, index) => ({
    id: index,
    timestamp: parseServerDate(event.created_at) ?? Date.now() + index,
    level: 'event',
    icon: '◌',
    message: event.title || event.event_type || 'timeline',
    detail: event.description || undefined,
    round: event.round_number,
    track: 'timeline',
    status: 'completed',
  }))
}

function clearLiveSurface() {
  sim.value = null
  sse.close()
  stopElapsedTimer()
  if (persistTimer) {
    clearTimeout(persistTimer)
    persistTimer = null
  }
  graphStore.reset()
  activityStore.clear()
  selectedEntity.value = null
  elapsedTime.value = 0
}

function readPersistedLiveState(id: string): PersistedSimulationLiveState | null {
  try {
    const raw = window.sessionStorage.getItem(liveStateKey(id))
    if (!raw) return null
    const parsed = JSON.parse(raw) as PersistedSimulationLiveState
    if (parsed.version !== LIVE_SESSION_VERSION) return null
    if (parsed.store?.simulationId && parsed.store.simulationId !== id) return null
    return parsed
  } catch {
    return null
  }
}

function restorePersistedLiveState(snapshot: PersistedSimulationLiveState | null, simulation: SimulationResponse) {
  if (!snapshot || simulation.status === 'completed' || simulation.status === 'failed') return

  const allowStatusRestore = snapshot.store.status === 'generating_report' || snapshot.store.status === 'disconnected'
  const allowPhaseRestore = snapshot.store.phase === 'report' || snapshot.store.phase === 'graphrag'

  store.restoreSnapshot(snapshot.store, {
    preserveStatus: !allowStatusRestore,
    preservePhase: !allowPhaseRestore,
    preservePipelineStage: true,
  })

  if (!graphStore.nodes.length && snapshot.graph?.nodes?.length) {
    graphStore.setFullState(snapshot.graph.nodes, snapshot.graph.edges)
  }
  if (activityStore.entries.length === 0 && snapshot.activity?.length) {
    activityStore.replaceEntries(snapshot.activity)
  }
}

function persistLiveState() {
  persistTimer = null
  const payload: PersistedSimulationLiveState = {
    version: LIVE_SESSION_VERSION,
    savedAt: Date.now(),
    store: store.toSnapshot(),
    graph: graphStore.toSnapshot(),
    activity: activityStore.toSnapshot(),
  }
  window.sessionStorage.setItem(liveStateKey(simId), JSON.stringify(payload))
}

function schedulePersist() {
  if (!sim.value || typeof window === 'undefined') return
  if (persistTimer) {
    clearTimeout(persistTimer)
  }
  persistTimer = setTimeout(() => {
    persistLiveState()
  }, 120)
}

function clearPersistedLiveState(id = simId) {
  window.sessionStorage.removeItem(liveStateKey(id))
}

function applySimulationState(simulation: SimulationResponse) {
  store.init(simId, simulation.mode, simulation.prompt_text)

  if (simulation.pipeline_stage) {
    store.setPipelineStage(simulation.pipeline_stage as any)
  }
  if (simulation.stage_progress) {
    store.setStageProgress(simulation.stage_progress)
  }

  const reportProgress = simulation.metadata?.report_progress as {
    status?: string
    sections?: string[]
    completed_sections?: string[]
    last_error?: string
  } | undefined

  if (simulation.status === 'completed') {
    store.setStatus('completed')
    store.setPhase('completed')
    store.setPipelineStage('completed')
  } else if (simulation.status === 'failed') {
    store.setError(simulation.error_message || '不明なエラー')
  } else if (simulation.status === 'generating_report') {
    store.setStatus('generating_report')
    store.setPhase('report')
  } else {
    store.setStatus(simulation.status || 'running')
    if (simulation.mode === 'pipeline' && simulation.pipeline_stage && simulation.pipeline_stage !== 'pending') {
      store.setPhase(simulation.pipeline_stage)
    } else if (simulation.status === 'running') {
      store.setPhase('world_building')
    }
  }

  if (reportProgress?.sections?.length) {
    const completed = new Set(reportProgress.completed_sections || [])
    store.setReportSectionsState(
      reportProgress.sections.map((name) => ({
        name,
        done: completed.has(name),
      })),
    )
    store.setReportError(reportProgress.last_error || '')
  }

  if (reportProgress?.status === 'running' && simulation.status !== 'completed') {
    store.setStatus('generating_report')
    store.setPhase('report')
  }
  if (reportProgress?.status === 'failed') {
    store.setPhase('report')
    store.setReportError(reportProgress.last_error || store.reportError)
  }
}

async function hydrateLiveData(simulation: SimulationResponse) {
  const [graphData, colonyData, timelineData] = await Promise.all([
    getSimulationGraph(simId).catch(() => null),
    simulation.swarm_id ? getSimulationColonies(simId).catch(() => []) : Promise.resolve([]),
    simulation.run_id ? getSimulationTimeline(simId).catch(() => []) : Promise.resolve([]),
  ])

  if (colonyData.length > 0) {
    store.setColonies(colonyData.map(mapColonyResponse))
  }

  if (activityStore.entries.length === 0 && timelineData.length > 0) {
    activityStore.replaceEntries(timelineToEntries(timelineData))
  }

  if (graphData?.nodes?.length) {
    graphStore.setFullState(graphData.nodes, graphData.edges)
  }

  if (graphStore.nodes.length > 0) {
    await nextTick()
    setFullGraph(graphStore.nodes, graphStore.edges)
  }
}

async function bootstrapSimulation() {
  clearLiveSurface()
  const persisted = readPersistedLiveState(simId)
  const e2eSimulation = (window as Window & {
    __AGENT_AI_E2E_SIMULATION__?: SimulationResponse
  }).__AGENT_AI_E2E_SIMULATION__

  if (e2eSimulation) {
    sim.value = e2eSimulation
    applySimulationState(sim.value)
    restorePersistedLiveState(persisted, sim.value)
    startElapsedTimer(sim.value.started_at)
    if (sim.value.status !== 'completed' && sim.value.status !== 'failed') {
      sse.start()
    }
    return
  }

  sim.value = await getSimulation(simId)
  applySimulationState(sim.value)
  restorePersistedLiveState(persisted, sim.value)
  startElapsedTimer(sim.value.started_at)
  await hydrateLiveData(sim.value)

  if (sim.value.status !== 'completed' && sim.value.status !== 'failed') {
    sse.start()
  }
}

onMounted(async () => {
  try {
    await bootstrapSimulation()
  } catch (error) {
    console.error('Simulation bootstrap failed:', error)
    store.init(simId, store.mode, store.promptText)
    store.setError('シミュレーション状態の取得に失敗しました。少し待ってから再読み込みしてください。')
  }
})

onUnmounted(() => {
  clearLiveSurface()
  graphStore.reset()
  activityStore.clear()
  societyGraphStore.reset()
  selectedEntity.value = null
})

watch(
  () => store.status,
  (newStatus) => {
    if (newStatus === 'completed' || newStatus === 'failed') {
      stopElapsedTimer()
    }
    if (newStatus === 'completed') {
      clearPersistedLiveState()
      router.push(`/sim/${simId}/results`)
    }
  },
)

watch(
  () => graphStore.pendingDiffs.length,
  () => {
    if (!graph.value || graphStore.pendingDiffs.length === 0) return
    const diffs = graphStore.consumePendingDiffs()
    for (const diff of diffs) {
      applyGraphDiff(diff)
    }
  },
)

watch(graph, (fg) => {
  if (!fg) return
  fg.onNodeClick((node: any) => {
    const storeNode = graphStore.nodes.find((n: any) => n.id === node.id)
    selectedEntity.value = storeNode || node
    const distance = 100
    const distRatio = 1 + distance / Math.hypot(node.x || 0, node.y || 0, node.z || 0)
    fg.cameraPosition(
      { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
      { x: node.x, y: node.y, z: node.z },
      1000,
    )
  })
})

watch(() => store.toSnapshot(), schedulePersist, { deep: true })
watch(() => graphStore.toSnapshot(), schedulePersist, { deep: true })
watch(() => activityStore.entries, schedulePersist, { deep: true })

function goToResults() {
  router.push(`/sim/${simId}/results`)
}
</script>

<template>
  <div class="sim-page">
    <!-- Progress Pipeline -->
    <SocietyProgress v-if="store.isSocietyMode" />
    <SimulationProgress v-else />

    <!-- Status Bar -->
    <div class="status-bar">
      <div class="status-left">
        <span class="status-mono">{{ store.isSocietyMode ? `${societyGraphStore.nodeCount} agents / ${societyGraphStore.edgeCount} edges` : `${graphStore.nodes.length} nodes / ${graphStore.edges.length} edges` }}</span>
        <span class="status-divider">|</span>
        <span class="status-mono">{{ formattedTime }}</span>
        <span class="status-divider">|</span>
        <span class="status-mono">{{ stageLabel }}</span>
        <template v-if="showColonyGrid">
          <span class="status-divider">|</span>
          <span class="status-mono">{{ store.completedColonies }}/{{ store.colonies.length }} Colony</span>
        </template>
      </div>
      <div class="status-right">
        <button
          v-if="store.status === 'completed'"
          class="btn btn-primary"
          @click="goToResults"
        >
          結果を表示
        </button>
      </div>
    </div>

    <div v-if="store.error" class="error-banner">
      {{ store.error }}
    </div>

    <!-- Unified Mode: Interim Results Dashboard -->
    <div v-if="store.isUnifiedMode && store.unifiedPhase !== 'idle'" class="unified-interim-panel">
      <!-- Phase 1 results: opinion distribution -->
      <div v-if="Object.keys(store.opinionDistribution).length > 0" class="pulse-summary">
        <div class="panel-header">
          <h3>社会反応速報</h3>
          <span class="panel-count">{{ store.unifiedPhaseIndex }}/{{ store.unifiedPhaseTotal }}</span>
        </div>
        <div class="stance-bars">
          <div
            v-for="(share, stance) in store.opinionDistribution"
            :key="stance"
            class="stance-bar-row"
          >
            <span class="stance-bar-label">{{ stance }}</span>
            <div class="stance-bar-track">
              <div
                class="stance-bar-fill"
                :style="{ width: `${(share as number) * 100}%` }"
              />
            </div>
            <span class="stance-bar-value">{{ ((share as number) * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>

      <!-- Phase 2 progress: council round -->
      <div v-if="store.unifiedPhase === 'council' || (store.unifiedPhase === 'synthesis' && societyGraphStore.currentRound > 0)" class="council-highlight">
        <div class="panel-header">
          <h3>評議会議論</h3>
        </div>
        <p class="council-round-info">Round {{ societyGraphStore.currentRound }} / 3</p>
      </div>
    </div>

    <!-- Society Opinion Distribution (inline, non-unified) -->
    <div v-else-if="store.isSocietyMode && Object.keys(store.opinionDistribution).length > 0" class="society-inline-panel">
      <div class="panel-header">
        <h3>意見分布</h3>
      </div>
      <OpinionDistribution :distribution="store.opinionDistribution" />
    </div>

    <!-- Main Layout -->
    <div class="sim-layout">
      <!-- Left: Graph + Colony Grid -->
      <div class="main-panel">
        <div class="graph-panel">
          <div class="panel-header">
            <h3>{{ store.isSocietyMode ? '3D Social Graph' : '3D Knowledge Graph' }}</h3>
            <div class="panel-metrics">
              <template v-if="store.isSocietyMode">
                <span class="metric"><span class="metric-val">{{ societyGraphStore.nodeCount }}</span> agents</span>
                <span class="metric"><span class="metric-val">{{ societyGraphStore.edgeCount }}</span> edges</span>
              </template>
              <template v-else>
                <span class="metric"><span class="metric-val">{{ graphStore.nodes.length }}</span> nodes</span>
                <span class="metric"><span class="metric-val">{{ graphStore.edges.length }}</span> edges</span>
              </template>
            </div>
          </div>
          <div class="graph-container" :class="graphContainerClass">
            <!-- Society mode: Live Social Graph -->
            <LiveSocietyGraph
              v-if="store.isSocietyMode"
              :simulation-id="simId"
            />
            <!-- Other modes: Knowledge Graph -->
            <template v-else>
              <div ref="graphCanvas" class="graph-canvas-host"></div>
              <div v-if="graphError" class="graph-error-state">
                <div class="graph-empty-shell">
                  <div class="graph-empty-eyebrow">Graph Unavailable</div>
                  <div class="graph-empty-title">3D グラフを表示できません</div>
                  <p class="graph-empty-detail">{{ graphError }}</p>
                </div>
              </div>
              <div v-else-if="graphStore.nodes.length === 0" class="graph-empty" :class="graphContainerClass">
                <div class="graph-empty-backdrop"></div>
                <div class="graph-empty-shell">
                  <div class="graph-empty-eyebrow">{{ emptyState.eyebrow }}</div>
                  <div class="graph-empty-title">{{ emptyState.title }}</div>
                  <p class="graph-empty-detail">{{ emptyState.detail }}</p>
                  <div class="loading-dots"><span></span><span></span><span></span></div>
                  <div class="graph-empty-pills">
                    <span class="graph-pill">{{ stageLabel }}</span>
                    <span v-if="store.totalRounds > 0" class="graph-pill">Round {{ store.currentRound }}/{{ store.totalRounds }}</span>
                    <span v-if="store.reportSections.length > 0" class="graph-pill">Report {{ store.completedReportSections }}/{{ store.reportSections.length }}</span>
                  </div>
                </div>
              </div>
              <div v-if="phaseOverlay && !graphError" class="phase-overlay">
                <span class="phase-icon">{{ phaseOverlay.icon }}</span>
                <span class="phase-label">{{ phaseOverlay.label }}</span>
              </div>
            </template>
          </div>
          <button v-if="!store.isSocietyMode && graphStore.nodes.length > 0 && !graphError" class="reset-camera-btn" @click="resetCamera" title="中心に戻す">&#8962;</button>
          <div v-if="!store.isSocietyMode && graphStore.nodes.length > 0 && !graphError" class="graph-legend">
            <span class="legend-item" v-for="(color, type) in entityTypeColors" :key="type">
              <span class="legend-dot" :style="{ background: color, boxShadow: `0 0 6px ${color}` }"></span>
              <span class="legend-label">{{ type }}</span>
            </span>
          </div>
        </div>

        <!-- Colony Grid (swarm stage in pipeline, or standalone swarm/hybrid) -->
        <div v-if="showColonyGrid" class="colony-overlay">
          <div class="panel-header">
            <h3>Colony Grid</h3>
            <span class="panel-count">{{ store.completedColonies }}/{{ store.colonies.length }}</span>
          </div>
          <ColonyGrid :colonies="store.colonies" />
        </div>
      </div>

      <!-- Right: Side Panel -->
      <div class="side-panel">
        <!-- Entity Detail -->
        <div v-if="selectedEntity" class="panel-card entity-detail">
          <div class="panel-header">
            <h3>Entity Inspector</h3>
            <button class="btn-icon" @click="selectedEntity = null">&#10005;</button>
          </div>
          <div class="entity-name">{{ selectedEntity.label }}</div>
          <div class="entity-meta">
            <span class="entity-type-badge">{{ selectedEntity.type }}</span>
            <span class="entity-score">重要度 {{ ((selectedEntity.importance_score || 0) * 100).toFixed(0) }}%</span>
          </div>
          <div class="detail-grid">
            <div v-if="selectedEntity.stance" class="detail-item">
              <span class="detail-key">立場</span>
              <span class="detail-val">{{ selectedEntity.stance }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-key">ステータス</span>
              <span class="detail-val">{{ selectedEntity.status }}</span>
            </div>
          </div>
        </div>

        <!-- Prompt Info -->
        <div v-if="store.promptText" class="panel-card">
          <div class="panel-header"><h3>Prompt</h3></div>
          <p class="prompt-text">{{ store.promptText }}</p>
        </div>

        <!-- Report Progress (WP6) -->
        <div v-if="store.reportSections.length > 0" class="panel-card">
          <div class="panel-header">
            <h3>Report Progress</h3>
            <span class="panel-count">{{ store.completedReportSections }}/{{ store.reportSections.length }}</span>
          </div>
          <div v-if="store.reportError" class="report-error-banner">
            {{ store.reportError }}
          </div>
          <div class="report-sections">
            <div
              v-for="(sec, i) in store.reportSections"
              :key="i"
              class="report-section-item"
              :class="{ done: sec.done }"
            >
              <span class="section-check">{{ sec.done ? '✓' : '…' }}</span>
              <span class="section-name">{{ sec.name }}</span>
            </div>
          </div>
        </div>

        <!-- Activity Feed -->
        <ActivityFeed :status="store.status" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.sim-page { display: flex; flex-direction: column; gap: var(--section-gap); }

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.75rem var(--panel-padding);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.status-left {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  font-family: var(--font-mono);
  font-size: 0.78rem;
}

.status-divider { color: var(--text-muted); }
.status-mono { color: var(--text-secondary); }

.status-right {
  display: flex;
  justify-content: flex-end;
  margin-left: auto;
}

.error-banner { padding: 0.75rem 1.25rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: var(--radius-sm); color: var(--danger); font-size: 0.85rem; }

.sim-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(18rem, 22rem);
  gap: 1rem;
  align-items: start;
  min-height: min(70vh, 52rem);
}

.main-panel { display: flex; flex-direction: column; gap: 0.75rem; }

.graph-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-bottom: 0.75rem;
}

.panel-header h3 { font-size: 0.82rem; font-weight: 600; }
.panel-metrics { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.metric { font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted); }
.metric-val { color: var(--accent); font-weight: 600; }

.graph-container {
  flex: 1;
  min-height: clamp(18rem, 42vw, 32rem);
  background: radial-gradient(ellipse at 30% 40%, #0d0d2b 0%, #060614 50%, #020208 100%);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(100,100,255,0.12);
  position: relative;
  overflow: hidden;
}

.graph-canvas-host {
  position: absolute;
  inset: 0;
}

.graph-container.tone-graphrag { background: radial-gradient(ellipse at 30% 30%, rgba(15, 60, 54, 0.88) 0%, #041118 48%, #02070b 100%); }
.graph-container.tone-report { background: radial-gradient(ellipse at 30% 35%, rgba(72, 36, 20, 0.9) 0%, #170a08 45%, #040405 100%); }
.graph-container.tone-swarm { background: radial-gradient(ellipse at 30% 35%, rgba(38, 25, 72, 0.92) 0%, #0b0618 48%, #020208 100%); }
.graph-container.tone-simulation { background: radial-gradient(ellipse at 30% 40%, rgba(29, 38, 82, 0.92) 0%, #070714 48%, #020208 100%); }

.graph-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 0.82rem;
  z-index: 1;
}
.graph-error-state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.25rem;
  z-index: 2;
}

.graph-empty-backdrop {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 50% 45%, rgba(255,255,255,0.08), transparent 36%),
    linear-gradient(135deg, rgba(255,255,255,0.03), transparent 50%);
  opacity: 0.7;
  animation: breathe 5s ease-in-out infinite;
}

.graph-empty-shell {
  position: relative;
  z-index: 1;
  max-width: 24rem;
  padding: 1.4rem 1.5rem;
  border-radius: 18px;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(8, 10, 22, 0.56);
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.65rem;
  text-align: center;
}

.graph-empty-eyebrow {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(200, 220, 255, 0.72);
}

.graph-empty-title {
  font-size: 1rem;
  font-weight: 600;
  color: rgba(245, 247, 255, 0.94);
}

.graph-empty-detail {
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.6;
  color: rgba(208, 214, 235, 0.72);
}

.loading-dots { display: flex; gap: 4px; }
.loading-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: typing-dot 1.4s ease-in-out infinite; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

.graph-empty-pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.45rem;
}

.graph-pill {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: rgba(220, 226, 245, 0.86);
  padding: 0.24rem 0.52rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.08);
}

.reset-camera-btn { position: absolute; top: 12px; right: 12px; z-index: 10; width: 32px; height: 32px; border-radius: 6px; border: 1px solid rgba(100,100,255,0.2); background: rgba(10,10,30,0.75); backdrop-filter: blur(8px); color: rgba(200,200,255,0.7); font-size: 1rem; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.2s; }
.reset-camera-btn:hover { background: rgba(30,30,80,0.85); color: #fff; border-color: rgba(100,100,255,0.4); }

.graph-legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: rgba(10,10,30,0.75);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(100,100,255,0.15);
  border-radius: 6px;
  z-index: 10;
}

.legend-item { display: flex; align-items: center; gap: 0.3rem; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.legend-label { font-family: var(--font-mono); font-size: 0.65rem; color: rgba(200,200,255,0.7); text-transform: uppercase; }

.colony-overlay { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-width: 0;
}

.panel-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }
.panel-count { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); background: rgba(255,255,255,0.04); padding: 0.1rem 0.4rem; border-radius: 4px; }
.panel-count.live { color: var(--success); background: rgba(34,197,94,0.1); }

.btn-icon { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.2rem 0.4rem; border-radius: 4px; }
.btn-icon:hover { color: var(--text-primary); background: rgba(255,255,255,0.06); }

.entity-name { font-size: 1.05rem; font-weight: 600; margin-bottom: 0.4rem; }
.entity-meta { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.entity-type-badge { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 4px; background: var(--accent-subtle); color: var(--accent); text-transform: uppercase; }
.entity-score { font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted); }
.detail-grid { display: flex; flex-direction: column; gap: 0.35rem; }
.detail-item { display: flex; justify-content: space-between; padding: 0.35rem 0; border-top: 1px solid var(--border); font-size: 0.8rem; }
.detail-key { color: var(--text-muted); }
.detail-val { color: var(--text-primary); font-weight: 500; }

.prompt-text { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap; }

/* Phase Overlay */
.phase-overlay {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 15;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 1rem;
  background: rgba(10, 10, 40, 0.82);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(100, 100, 255, 0.2);
  border-radius: 20px;
  pointer-events: none;
}

.phase-icon {
  font-size: 0.9rem;
  animation: breathe 2s ease-in-out infinite;
}

.phase-label {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: rgba(200, 200, 255, 0.9);
  white-space: nowrap;
}

.phase-fade-enter-active,
.phase-fade-leave-active {
  transition: opacity 0.4s ease, transform 0.4s ease;
}
.phase-fade-enter-from { opacity: 0; transform: translateX(-50%) translateY(-8px); }
.phase-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

/* Report Sections (WP6) */
.report-sections {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.report-section-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
  padding: 0.2rem 0;
}

.report-section-item.done {
  color: var(--success);
}

.report-error-banner {
  margin-bottom: 0.6rem;
  padding: 0.55rem 0.7rem;
  border-radius: 8px;
  border: 1px solid rgba(239,68,68,0.2);
  background: rgba(239,68,68,0.08);
  color: var(--danger);
  font-size: 0.72rem;
  line-height: 1.5;
}

.section-check {
  width: 1.2em;
  text-align: center;
}

.section-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes typing-dot {
  0%, 80%, 100% { opacity: 0.3; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-4px); }
}

@keyframes breathe {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 0.95; transform: scale(1.02); }
}

@media (max-width: 1200px) {
  .sim-layout {
    grid-template-columns: minmax(0, 1fr) minmax(17rem, 20rem);
  }
}

@media (max-width: 900px) {
  .sim-layout {
    grid-template-columns: 1fr;
    min-height: auto;
  }

  .status-right {
    margin-left: 0;
  }
}

@media (max-width: 640px) {
  .status-bar {
    align-items: stretch;
  }

  .status-right {
    width: 100%;
  }

  .status-right :deep(.btn) {
    width: 100%;
  }

  .graph-panel,
  .colony-overlay,
  .panel-card {
    padding: 0.95rem;
  }

  .graph-container {
    min-height: 18rem;
  }

  .reset-camera-btn {
    top: 10px;
    right: 10px;
  }

  .graph-legend {
    left: 10px;
    right: 10px;
    bottom: 10px;
  }

  .entity-meta,
  .detail-item {
    flex-wrap: wrap;
    gap: 0.35rem;
  }
}

.society-inline-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
}

.unified-interim-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.pulse-summary {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
}

.stance-bars {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.stance-bar-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.stance-bar-label {
  font-size: 0.76rem;
  font-weight: 500;
  color: var(--text-secondary);
  width: 5.5rem;
  flex-shrink: 0;
  text-align: right;
}

.stance-bar-track {
  flex: 1;
  height: 8px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
  overflow: hidden;
}

.stance-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--success), var(--accent));
  border-radius: 4px;
  transition: width 0.6s ease;
}

.stance-bar-value {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-muted);
  width: 2.5rem;
  flex-shrink: 0;
}

.council-highlight {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
}

.council-round-info {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  color: var(--text-secondary);
}
</style>
