<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScenarioPairStore } from '../stores/scenarioPairStore'
import { useScenarioPairSSE } from '../composables/useScenarioPairSSE'
import ComparisonBrief from '../components/ComparisonBrief.vue'
import CoalitionMap from '../components/CoalitionMap.vue'
import OpinionShiftTable from '../components/OpinionShiftTable.vue'
import AuditTimeline from '../components/AuditTimeline.vue'
import type { OpinionShift } from '../components/OpinionShiftTable.vue'
import type { AuditEvent } from '../components/AuditTimeline.vue'

const route = useRoute()
const router = useRouter()
const scenarioId = route.params.id as string

const store = useScenarioPairStore()
const loading = ref(true)
const fetchError = ref('')

const { events, baselineStatus, interventionStatus, isComplete, start: startSSE } =
  useScenarioPairSSE(scenarioId)

const isRunning = computed(() =>
  baselineStatus.value === 'running' || interventionStatus.value === 'running',
)
const isFailed = computed(() =>
  store.currentPair?.status === 'failed' ||
  baselineStatus.value === 'failed' ||
  interventionStatus.value === 'failed',
)

const eventLabels: Record<string, string> = {
  run_started: 'シミュレーション開始',
  phase_changed: 'フェーズ移行',
  round_completed: 'ラウンド完了',
  colony_started: 'Colony 開始',
  colony_completed: 'Colony 完了',
  society_activation_progress: '社会反応を分析中',
  meeting_dialogue: '評議会で議論中',
  report_started: 'レポート生成開始',
  report_completed: 'レポート完了',
}

function latestEventLabel(role: 'baseline' | 'intervention'): string {
  const roleEvents = events.value.filter(e => e.role === role)
  if (roleEvents.length === 0) return '接続中...'
  const last = roleEvents[roleEvents.length - 1]
  return eventLabels[last.event_type] || last.event_type
}

function formatStatus(status: string): string {
  switch (status) {
    case 'created':
      return '作成済み'
    case 'queued':
      return '準備中'
    case 'pending':
      return '待機中'
    case 'running':
      return '実行中'
    case 'completed':
      return '完了'
    case 'failed':
      return '失敗'
    case 'idle':
      return '待機中'
    default:
      return status
  }
}

const opinionShifts = computed<OpinionShift[]>(() => {
  if (!store.comparisonResult?.opinion_shifts_top5) return []
  return store.comparisonResult.opinion_shifts_top5.map((s: Record<string, unknown>) => ({
    agent_name: String(s.agent_name || ''),
    before: String(s.before || ''),
    after: String(s.after || ''),
    reasoning: String(s.reasoning || ''),
  }))
})

const coalitionMap = computed<Record<string, unknown>>(() =>
  store.comparisonResult?.coalition_map || {},
)

const auditEvents = computed<AuditEvent[]>(() => {
  return events.value.map((e, i) => ({
    id: `evt-${i}`,
    agent_id: String(e.payload?.agent_id || e.role),
    agent_name: String(e.payload?.agent_name || e.role),
    event_type: e.event_type,
    reasoning: String(e.payload?.summary || e.payload?.description || e.event_type),
    timestamp: new Date(e.timestamp).toLocaleTimeString(),
  }))
})

onMounted(async () => {
  try {
    await store.fetchPair(scenarioId)
    const pair = store.currentPair

    if (!pair) {
      fetchError.value = '比較データが見つかりません'
      return
    }

    if (pair.status === 'completed') {
      await store.fetchComparison(scenarioId)
    } else if (pair.status !== 'failed') {
      startSSE()
    }
  } catch (err: any) {
    const status = err.response?.status
    if (status === 404) {
      fetchError.value = '比較データが見つかりません'
    } else {
      fetchError.value = '比較データの読み込みに失敗しました'
    }
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="scenario-page">
    <header class="page-header">
      <button class="btn btn-ghost" @click="router.push('/')">
        &larr; 戻る
      </button>
      <div class="header-info">
        <h1 class="page-title">2条件の比較結果</h1>
        <p v-if="store.currentPair" class="page-subtitle">
          {{ store.currentPair.decision_context }}
        </p>
        <p class="page-caption">同じ母集団で、「介入なし」と「介入あり」を比べています</p>
      </div>
      <div v-if="store.currentPair" class="header-status">
        <span
          class="status-badge"
          :class="{
            'status-running': isRunning,
            'status-completed': isComplete || store.currentPair.status === 'completed',
            'status-failed': store.currentPair.status === 'failed',
          }"
        >
          {{ isRunning ? '実行中' : formatStatus(store.currentPair.status) }}
        </span>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="loading" class="page-loading">
      <div class="spinner" />
      <p class="loading-text">比較データを読み込んでいます...</p>
    </div>

    <!-- Error -->
    <div v-else-if="fetchError" class="page-error card">
      <p class="error-text">{{ fetchError }}</p>
      <button class="btn btn-primary" @click="router.push('/')">ホームへ戻る</button>
    </div>

    <!-- Content -->
    <template v-else>
      <!-- Progress for running simulations -->
      <div v-if="isRunning" class="progress-section">
        <div class="progress-grid">
          <div class="card">
            <h3 class="progress-label">介入なし</h3>
            <div class="progress-status">
              <span class="status-dot" :class="'dot-' + baselineStatus" />
              {{ formatStatus(baselineStatus) }}
            </div>
            <div class="sse-progress">
              <div class="sse-progress-bar"><div class="sse-progress-fill" /></div>
              <p class="sse-progress-label">{{ latestEventLabel('baseline') }}</p>
            </div>
          </div>
          <div class="card">
            <h3 class="progress-label">介入あり</h3>
            <div class="progress-status">
              <span class="status-dot" :class="'dot-' + interventionStatus" />
              {{ formatStatus(interventionStatus) }}
            </div>
            <div class="sse-progress">
              <div class="sse-progress-bar"><div class="sse-progress-fill" /></div>
              <p class="sse-progress-label">{{ latestEventLabel('intervention') }}</p>
            </div>
          </div>
        </div>
      </div>

      <div
        v-else-if="isFailed"
        class="card page-error"
      >
        <p class="error-text">比較シミュレーションの実行に失敗しました。</p>
      </div>

      <!-- Completed: show comparison -->
      <template v-if="store.hasComparison && store.comparisonResult">
        <section class="section">
          <ComparisonBrief :comparison="store.comparisonResult" />
        </section>

        <section v-if="Object.keys(coalitionMap).length > 0" class="section card">
          <CoalitionMap :coalition-map="coalitionMap" />
        </section>

        <section v-if="opinionShifts.length > 0" class="section card">
          <OpinionShiftTable :shifts="opinionShifts" />
        </section>

        <section v-if="auditEvents.length > 0" class="section card">
          <AuditTimeline :events="auditEvents" />
        </section>
      </template>

      <!-- No comparison yet and not running -->
      <div
        v-if="!store.hasComparison && !isRunning && !isFailed && !loading"
        class="card page-waiting"
      >
        <p class="waiting-text">2つの分析が終わると、ここに違いが表示されます。</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.scenario-page {
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: var(--page-padding);
  display: flex;
  flex-direction: column;
  gap: var(--section-gap);
  min-height: 100vh;
}

.page-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
}

.header-info {
  flex: 1;
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: 700;
}

.page-subtitle {
  margin-top: var(--space-1);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}

.page-caption {
  margin-top: var(--space-1);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.header-status {
  flex-shrink: 0;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}

.status-running {
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent);
}

.status-completed {
  background: rgba(34, 197, 94, 0.15);
  color: var(--success);
}

.status-failed {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
}

/* Loading */
.page-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding: var(--space-16) 0;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Error */
.page-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-8);
  text-align: center;
}

.error-text {
  font-size: var(--text-sm);
  color: var(--danger);
}

/* Progress */
.progress-section {
  animation: fade-in 0.4s ease-out;
}

.progress-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--section-gap);
}

.progress-label {
  font-size: var(--text-sm);
  font-weight: 600;
  margin-bottom: var(--space-2);
}

.progress-status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--text-secondary);
  margin-bottom: var(--space-3);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot-idle { background: var(--text-muted); }
.dot-running { background: var(--accent); animation: pulse-dot 1.5s infinite; }
.dot-completed { background: var(--success); }
.dot-failed { background: var(--danger); }

/* SSE Progress */
.sse-progress {
  padding: 0.75rem 1rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.sse-progress-bar {
  height: 3px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.sse-progress-fill {
  height: 100%;
  width: 40%;
  background: linear-gradient(90deg, var(--accent), var(--highlight));
  border-radius: 2px;
  animation: indeterminate 1.5s ease-in-out infinite;
}

.sse-progress-label {
  font-size: 0.72rem;
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

/* Sections */
.section {
  animation: fade-in 0.4s ease-out;
}

/* Waiting */
.page-waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  text-align: center;
}

.waiting-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
  }

  .progress-grid {
    grid-template-columns: 1fr;
  }
}
</style>
