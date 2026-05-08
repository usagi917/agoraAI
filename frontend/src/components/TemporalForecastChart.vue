<script setup lang="ts">
import { computed } from 'vue'

interface TimelineEntry {
  key: string
  label: string
  delta_days: number
  t_index: number
  distribution: Record<string, number>
}

const props = defineProps<{
  timeline: TimelineEntry[]
  stances?: string[]
}>()

const stances = computed(() => {
  if (props.stances && props.stances.length) return props.stances
  const set = new Set<string>()
  for (const e of props.timeline) {
    Object.keys(e.distribution).forEach((s) => set.add(s))
  }
  return Array.from(set)
})
</script>

<template>
  <section class="temporal-forecast-chart">
    <h3>時系列予測</h3>
    <table>
      <thead>
        <tr>
          <th>Horizon</th>
          <th v-for="s in stances" :key="s">{{ s }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="entry in timeline" :key="entry.key">
          <td>{{ entry.label }}</td>
          <td v-for="s in stances" :key="s">
            {{ (entry.distribution[s] ?? 0).toFixed(3) }}
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
table {
  border-collapse: collapse;
  width: 100%;
}
th,
td {
  border: 1px solid #ddd;
  padding: 4px 8px;
  text-align: right;
}
th:first-child,
td:first-child {
  text-align: left;
}
</style>
