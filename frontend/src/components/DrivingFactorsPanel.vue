<script setup lang="ts">
interface Factor {
  stance: string
  delta: number
}

interface TimelineEntry {
  key: string
  label: string
  driving_factors: Factor[]
}

defineProps<{
  timeline: TimelineEntry[]
}>()
</script>

<template>
  <section class="driving-factors-panel">
    <h3>駆動要因</h3>
    <ul class="factor-list">
      <li v-for="entry in timeline" :key="entry.key" class="factor-step">
        <strong>{{ entry.label }}</strong>
        <ul>
          <li v-for="f in entry.driving_factors" :key="f.stance">
            {{ f.stance }}:
            <span :class="f.delta >= 0 ? 'pos' : 'neg'">
              {{ f.delta >= 0 ? '+' : '' }}{{ f.delta.toFixed(3) }}
            </span>
          </li>
        </ul>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.factor-step {
  margin-bottom: 0.5rem;
}
.pos {
  color: #2a7;
}
.neg {
  color: #d44;
}
</style>
