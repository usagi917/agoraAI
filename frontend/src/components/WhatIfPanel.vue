<script setup lang="ts">
interface WhatIfEntry {
  key: string
  delta: Record<string, number>
  baseline: Record<string, number>
  alternative: Record<string, number>
}

defineProps<{
  whatIf: WhatIfEntry[]
}>()
</script>

<template>
  <section class="what-if-panel">
    <h3>What-if 分析</h3>
    <div v-for="entry in whatIf" :key="entry.key" class="step-block">
      <h4>{{ entry.key }}</h4>
      <table>
        <thead>
          <tr>
            <th>Stance</th>
            <th>Baseline</th>
            <th>Alternative</th>
            <th>Δ</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(value, stance) in entry.delta" :key="stance">
            <td>{{ stance }}</td>
            <td>{{ (entry.baseline[stance] ?? 0).toFixed(3) }}</td>
            <td>{{ (entry.alternative[stance] ?? 0).toFixed(3) }}</td>
            <td :class="value >= 0 ? 'pos' : 'neg'">
              {{ value >= 0 ? '+' : '' }}{{ value.toFixed(3) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
table {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 1rem;
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
.pos {
  color: #2a7;
}
.neg {
  color: #d44;
}
</style>
