<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSimulationSSE } from '../composables/useSimulationSSE'
import { useSimulationStore } from '../stores/simulationStore'
import { useSocietyGraphStore } from '../stores/societyGraphStore'
import { useValidationStore } from '../stores/validationStore'
import LiveSocietyGraph from '../components/LiveSocietyGraph.vue'
import ValidationVerdictCard from '../components/ValidationVerdictCard.vue'
import DistributionCompare from '../components/DistributionCompare.vue'
import ConditionStrip from '../components/ConditionStrip.vue'
import OpinionBubbles from '../components/OpinionBubbles.vue'

const route = useRoute()
const router = useRouter()
const validation = useValidationStore()
const simulation = useSimulationStore()
const societyGraph = useSocietyGraphStore()
const initialSimulationId = String(route.params.id || '')
const sse = initialSimulationId ? useSimulationSSE(initialSimulationId) : null

const activeSimulationId = computed(() =>
  String(route.params.id || validation.runningSimulationId || ''),
)

const canRun = computed(() =>
  !!validation.selectedTopic && !validation.starting && simulation.status !== 'running',
)

const sampleReasons = computed(() => validation.report?.sample_reasons || [])

function closeSse() {
  sse?.close()
}

function startSse(simId: string) {
  if (!sse || simId !== initialSimulationId) return
  closeSse()
  simulation.init(simId, 'standard', validation.selectedTopic?.theme || '')
  societyGraph.reset()
  sse.start()
}

async function runValidation() {
  const simId = await validation.startValidation()
  if (!simId) return
  await router.push(`/validate/${simId}`)
}

async function loadDirectReport(simId: string) {
  validation.runningSimulationId = simId
  try {
    await validation.loadReport(simId)
    simulation.setStatus('completed')
  } catch {
    startSse(simId)
  }
}

onMounted(async () => {
  await validation.loadTopics()
  if (activeSimulationId.value) {
    await loadDirectReport(activeSimulationId.value)
  }
})

watch(() => simulation.status, async (status) => {
  if (status === 'completed' && activeSimulationId.value && !validation.report) {
    await validation.loadReport(activeSimulationId.value)
  }
})

onUnmounted(() => closeSse())
</script>

<template>
  <div class="validate-page">
    <section class="validation-toolbar">
      <div class="topic-control">
        <label for="validation-topic">検証トピック</label>
        <select
          id="validation-topic"
          v-model="validation.selectedSurveyId"
          :disabled="validation.loadingTopics || validation.starting"
        >
          <option
            v-for="topic in validation.topics"
            :key="topic.survey_id"
            :value="topic.survey_id"
          >
            {{ topic.theme }} / {{ topic.source_origin === 'cross_source' ? 'cross-source' : 'BOJ' }}
          </option>
        </select>
      </div>
      <button
        class="btn btn-primary run-button"
        type="button"
        :disabled="!canRun"
        @click="runValidation"
      >
        検証を実行
      </button>
    </section>

    <p v-if="validation.error" class="validation-error">
      {{ validation.error }}
      <button type="button" @click="runValidation">再試行</button>
    </p>
    <p v-if="simulation.status === 'disconnected'" class="connection-banner">
      接続が切れました。再接続を試行しています。
    </p>

    <section class="validate-workspace">
      <div class="graph-hero">
        <LiveSocietyGraph
          v-if="activeSimulationId"
          :simulation-id="activeSimulationId"
        />
        <div v-else class="graph-placeholder">
          <span>{{ validation.selectedTopic?.theme || '検証トピック' }}</span>
        </div>
        <OpinionBubbles :opinions="sampleReasons" />
      </div>

      <aside class="validation-overlay">
        <ValidationVerdictCard
          v-if="validation.report"
          :verdict="validation.report.verdict"
          :jsd="validation.report.jsd"
          :emd="validation.report.emd"
          :brier="validation.report.brier"
        />
        <DistributionCompare
          v-if="validation.report"
          :predicted="validation.report.predicted"
          :actual="validation.report.actual"
        />
        <ConditionStrip
          v-if="validation.report"
          :evaluations="validation.report.evaluations"
        />
      </aside>
    </section>
  </div>
</template>

<style scoped>
.validate-page {
  display: grid;
  gap: 1rem;
}

.validation-toolbar {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 0;
}

.topic-control {
  display: grid;
  gap: 0.35rem;
  min-width: min(26rem, 100%);
}

.topic-control label {
  color: var(--text-secondary);
  font-size: 0.78rem;
}

.topic-control select {
  min-height: 2.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-secondary);
  color: var(--text-primary);
  padding: 0 0.75rem;
}

.run-button {
  min-height: 2.5rem;
  white-space: nowrap;
}

.validation-error,
.connection-banner {
  border: 1px solid rgba(245, 158, 11, 0.28);
  border-radius: var(--radius);
  color: var(--warning);
  background: rgba(245, 158, 11, 0.08);
  padding: 0.7rem 0.9rem;
  font-size: 0.85rem;
}

.validation-error button {
  margin-left: 0.75rem;
  color: var(--accent);
  background: transparent;
  border: 0;
  cursor: pointer;
}

.validate-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(21rem, 28rem);
  gap: 1rem;
  min-height: min(72vh, 48rem);
}

.graph-hero {
  position: relative;
  min-height: min(72vh, 48rem);
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-secondary);
}

.graph-hero :deep(.live-society-graph) {
  height: 100%;
  min-height: inherit;
}

.graph-placeholder {
  height: 100%;
  min-height: inherit;
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  background:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    var(--bg-secondary);
  background-size: 32px 32px;
}

.validation-overlay {
  display: grid;
  align-content: start;
  gap: 0.75rem;
}

@media (max-width: 980px) {
  .validation-toolbar,
  .validate-workspace {
    grid-template-columns: 1fr;
  }

  .validation-toolbar {
    display: grid;
  }

  .validate-workspace {
    min-height: auto;
  }

  .graph-hero {
    min-height: 34rem;
  }
}
</style>
