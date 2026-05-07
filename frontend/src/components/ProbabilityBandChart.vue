<script setup lang="ts">
import { computed } from 'vue'

interface CIBand {
  lower: number
  median: number
  upper: number
}

interface CILevel {
  [stance: string]: CIBand
}

interface CredibleIntervals {
  '50'?: CILevel
  '80'?: CILevel
  '95'?: CILevel
}

const props = defineProps<{
  intervals: CredibleIntervals
  stances: string[]
  title?: string
}>()

const stances = computed(() => props.stances ?? Object.keys(props.intervals['50'] ?? {}))
</script>

<template>
  <section class="probability-band-chart">
    <h3 v-if="props.title">{{ props.title }}</h3>
    <table class="band-table">
      <thead>
        <tr>
          <th>Stance</th>
          <th>50% lower</th>
          <th>50% median</th>
          <th>50% upper</th>
          <th>95% lower</th>
          <th>95% upper</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="stance in stances" :key="stance">
          <td>{{ stance }}</td>
          <td>{{ (intervals['50']?.[stance]?.lower ?? 0).toFixed(3) }}</td>
          <td>{{ (intervals['50']?.[stance]?.median ?? 0).toFixed(3) }}</td>
          <td>{{ (intervals['50']?.[stance]?.upper ?? 0).toFixed(3) }}</td>
          <td>{{ (intervals['95']?.[stance]?.lower ?? 0).toFixed(3) }}</td>
          <td>{{ (intervals['95']?.[stance]?.upper ?? 0).toFixed(3) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.probability-band-chart {
  font-family: var(--font-sans, system-ui);
}
.band-table {
  border-collapse: collapse;
  width: 100%;
}
.band-table th,
.band-table td {
  border: 1px solid #ddd;
  padding: 4px 8px;
  text-align: right;
}
.band-table th:first-child,
.band-table td:first-child {
  text-align: left;
}
</style>
