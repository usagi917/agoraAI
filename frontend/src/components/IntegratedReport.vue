<script setup lang="ts">
import TemporalForecastChart from './TemporalForecastChart.vue'
import DrivingFactorsPanel from './DrivingFactorsPanel.vue'
import WhatIfPanel from './WhatIfPanel.vue'

interface TimelineEntry {
  key: string
  label: string
  delta_days: number
  t_index: number
  distribution: Record<string, number>
  driving_factors: { stance: string; delta: number }[]
}

interface WhatIfEntry {
  key: string
  delta: Record<string, number>
  baseline: Record<string, number>
  alternative: Record<string, number>
}

interface Report {
  theme: string
  timeline: TimelineEntry[]
  summary: {
    long_term_shift: Record<string, number>
    horizons: number
    from?: string
    to?: string
  }
  what_if?: WhatIfEntry[]
}

defineProps<{
  report: Report
}>()
</script>

<template>
  <article class="integrated-report">
    <header>
      <h2>{{ report.theme }}</h2>
      <p v-if="report.summary?.from && report.summary?.to">
        {{ report.summary.from }} → {{ report.summary.to }} ({{ report.summary.horizons }} horizons)
      </p>
    </header>

    <TemporalForecastChart :timeline="report.timeline" />
    <DrivingFactorsPanel :timeline="report.timeline" />
    <WhatIfPanel v-if="report.what_if" :what-if="report.what_if" />

    <section class="long-term-shift">
      <h3>長期 Shift (last - first)</h3>
      <ul>
        <li v-for="(value, stance) in report.summary.long_term_shift" :key="stance">
          {{ stance }}:
          <span :class="value >= 0 ? 'pos' : 'neg'">
            {{ value >= 0 ? '+' : '' }}{{ value.toFixed(3) }}
          </span>
        </li>
      </ul>
    </section>
  </article>
</template>

<style scoped>
.integrated-report {
  display: grid;
  gap: 1.5rem;
}
.pos {
  color: #2a7;
}
.neg {
  color: #d44;
}
</style>
