<script setup lang="ts">
import { computed } from 'vue'

interface Scenario {
  description: string
  probability: number
  ci: [number, number]
  agreementRatio?: number
}

const props = defineProps<{
  scenarios: Scenario[]
}>()

const maxProbability = computed(() =>
  Math.max(...props.scenarios.map(s => s.probability), 0.01)
)

const barColor = (prob: number) => {
  if (prob >= 0.6) return 'var(--accent)'
  if (prob >= 0.3) return 'var(--warning)'
  return 'var(--text-muted)'
}
</script>

<template>
  <div class="probability-chart">
    <div
      v-for="(scenario, index) in scenarios"
      :key="index"
      class="scenario-row"
    >
      <div class="scenario-label">
        <span class="scenario-index">S{{ index + 1 }}</span>
        <span class="scenario-description">{{ scenario.description }}</span>
      </div>
      <div class="scenario-bar-container">
        <div class="scenario-bar-bg">
          <!-- CI range -->
          <div
            class="ci-range"
            :style="{
              left: `${scenario.ci[0] * 100}%`,
              width: `${(scenario.ci[1] - scenario.ci[0]) * 100}%`,
            }"
          ></div>
          <!-- Main bar -->
          <div
            class="scenario-bar"
            :style="{
              width: `${(scenario.probability / maxProbability) * 100}%`,
              background: barColor(scenario.probability),
            }"
          ></div>
        </div>
        <span class="probability-value">
          {{ (scenario.probability * 100).toFixed(0) }}%
        </span>
      </div>
      <div class="scenario-meta" v-if="scenario.agreementRatio !== undefined">
        <span class="agreement" title="Colony 間合意率">
          合意 {{ (scenario.agreementRatio * 100).toFixed(0) }}%
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.probability-chart {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.scenario-row {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.scenario-label {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.scenario-index {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text-muted);
  flex-shrink: 0;
}

.scenario-description {
  font-size: 0.82rem;
  color: var(--text-primary);
  line-height: 1.3;
}

.scenario-bar-container {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.scenario-bar-bg {
  flex: 1;
  height: 8px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 4px;
  overflow: hidden;
  position: relative;
}

.ci-range {
  position: absolute;
  top: 0;
  height: 100%;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 4px;
}

.scenario-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
  position: relative;
  z-index: 1;
}

.probability-value {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--text-primary);
  min-width: 3rem;
  text-align: right;
}

.scenario-meta {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.agreement {
  font-size: 0.68rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

@media (max-width: 640px) {
  .scenario-bar-container {
    gap: 0.5rem;
  }

  .probability-value {
    min-width: 2.5rem;
    font-size: 0.76rem;
  }
}
</style>
