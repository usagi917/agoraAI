<script setup lang="ts">
interface Scenario {
  description: string
  scenarioScore: number
  ci: [number, number]
  supportRatio: number
  modelConfidenceMean: number
  supportingColonies: number
  totalColonies: number
  claimCount: number
}

const props = defineProps<{
  scenarios: Scenario[]
}>()
</script>

<template>
  <div class="scenario-compare">
    <table class="compare-table">
      <thead>
        <tr>
          <th>シナリオ</th>
          <th>スコア</th>
          <th>95% CI</th>
          <th>支持率</th>
          <th>モデル信頼度</th>
          <th>Colony</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(s, i) in scenarios" :key="i">
          <td class="scenario-cell">
            <span class="scenario-idx">S{{ i + 1 }}</span>
            {{ s.description }}
          </td>
          <td class="number-cell highlight">
            {{ (s.scenarioScore * 100).toFixed(1) }}%
          </td>
          <td class="number-cell">
            {{ (s.ci[0] * 100).toFixed(0) }}-{{ (s.ci[1] * 100).toFixed(0) }}%
          </td>
          <td class="number-cell">
            {{ (s.supportRatio * 100).toFixed(0) }}%
          </td>
          <td class="number-cell">
            {{ (s.modelConfidenceMean * 100).toFixed(0) }}%
          </td>
          <td class="number-cell">
            {{ s.supportingColonies }}/{{ s.totalColonies }}
          </td>
        </tr>
      </tbody>
    </table>

    <div class="scenario-cards">
      <article v-for="(s, i) in scenarios" :key="`card-${i}`" class="scenario-card">
        <div class="scenario-card-header">
          <span class="scenario-idx">S{{ i + 1 }}</span>
          <span class="scenario-card-probability">{{ (s.scenarioScore * 100).toFixed(1) }}%</span>
        </div>
        <p class="scenario-card-description">{{ s.description }}</p>
        <dl class="scenario-card-metrics">
          <div class="metric-row">
            <dt>95% CI</dt>
            <dd>{{ (s.ci[0] * 100).toFixed(0) }}-{{ (s.ci[1] * 100).toFixed(0) }}%</dd>
          </div>
          <div class="metric-row">
            <dt>支持率</dt>
            <dd>{{ (s.supportRatio * 100).toFixed(0) }}%</dd>
          </div>
          <div class="metric-row">
            <dt>モデル信頼度</dt>
            <dd>{{ (s.modelConfidenceMean * 100).toFixed(0) }}%</dd>
          </div>
          <div class="metric-row">
            <dt>Colony</dt>
            <dd>{{ s.supportingColonies }}/{{ s.totalColonies }}</dd>
          </div>
        </dl>
      </article>
    </div>
  </div>
</template>

<style scoped>
.scenario-compare {
  overflow-x: auto;
}

.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
  min-width: 42rem;
}

.compare-table th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.compare-table td {
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  color: var(--text-secondary);
}

.compare-table tr:hover td {
  background: rgba(255, 255, 255, 0.02);
}

.scenario-cell {
  max-width: 300px;
  line-height: 1.3;
  color: var(--text-primary);
}

.scenario-idx {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--text-muted);
  margin-right: 0.4rem;
}

.number-cell {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  white-space: nowrap;
}

.number-cell.highlight {
  color: var(--accent);
  font-weight: 700;
}

.scenario-cards {
  display: none;
  flex-direction: column;
  gap: 0.75rem;
}

.scenario-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.9rem;
  background: rgba(255, 255, 255, 0.02);
}

.scenario-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.scenario-card-probability {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--accent);
}

.scenario-card-description {
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--text-primary);
}

.scenario-card-metrics {
  display: grid;
  gap: 0.45rem;
  margin-top: 0.75rem;
}

.metric-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.76rem;
}

.metric-row dt {
  color: var(--text-muted);
}

.metric-row dd {
  margin: 0;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  text-align: right;
}

@media (max-width: 640px) {
  .scenario-compare {
    overflow: visible;
  }

  .compare-table {
    display: none;
  }

  .scenario-cards {
    display: flex;
  }
}
</style>
