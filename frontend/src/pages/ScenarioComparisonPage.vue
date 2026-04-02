<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScenarioPairStore } from '../stores/scenarioPairStore'
import { useScenarioPairSSE } from '../composables/useScenarioPairSSE'
import ComparisonBrief from '../components/ComparisonBrief.vue'
import CoalitionMap from '../components/CoalitionMap.vue'
import OpinionShiftTable from '../components/OpinionShiftTable.vue'
import AuditTimeline from '../components/AuditTimeline.vue'
import SimulationProgress from '../components/SimulationProgress.vue'
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
      fetchError.value = 'Scenario pair not found'
      return
    }

    if (pair.status === 'completed') {
      await store.fetchComparison(scenarioId)
    } else {
      startSSE()
    }
  } catch (err: any) {
    fetchError.value = err.message || 'Failed to load scenario pair'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="scenario-page">
    <header class="page-header">
      <button class="btn btn-ghost" @click="router.push('/')">
        &larr; Back
      </button>
      <div class="header-info">
        <h1 class="page-title">Scenario Comparison</h1>
        <p v-if="store.currentPair" class="page-subtitle">
          {{ store.currentPair.decision_context }}
        </p>
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
          {{ isRunning ? 'Running' : store.currentPair.status }}
        </span>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="loading" class="page-loading">
      <div class="spinner" />
      <p class="loading-text">Loading scenario pair...</p>
    </div>

    <!-- Error -->
    <div v-else-if="fetchError" class="page-error card">
      <p class="error-text">{{ fetchError }}</p>
      <button class="btn btn-primary" @click="router.push('/')">Home</button>
    </div>

    <!-- Content -->
    <template v-else>
      <!-- Progress for running simulations -->
      <div v-if="isRunning" class="progress-section">
        <div class="progress-grid">
          <div class="card">
            <h3 class="progress-label">Baseline</h3>
            <div class="progress-status">
              <span class="status-dot" :class="'dot-' + baselineStatus" />
              {{ baselineStatus }}
            </div>
            <SimulationProgress />
          </div>
          <div class="card">
            <h3 class="progress-label">Intervention</h3>
            <div class="progress-status">
              <span class="status-dot" :class="'dot-' + interventionStatus" />
              {{ interventionStatus }}
            </div>
            <SimulationProgress />
          </div>
        </div>
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
        v-if="!store.hasComparison && !isRunning && !loading"
        class="card page-waiting"
      >
        <p class="waiting-text">Comparison results will appear here once both simulations complete.</p>
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
