<script setup lang="ts">
import { computed } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

const store = useCognitiveStore()

const relations = computed(() => store.tomRelations)

function trustColor(trust: number): string {
  if (trust >= 0.7) return '#27ae60'
  if (trust >= 0.4) return '#f39c12'
  return '#e74c3c'
}
</script>

<template>
  <div class="tom-map">
    <h3>Theory of Mind マップ</h3>

    <div v-if="relations.length === 0" class="no-data">
      ToMデータがありません
    </div>

    <div v-else class="relation-grid">
      <div
        v-for="rel in relations"
        :key="`${rel.observer}-${rel.target}`"
        class="tom-card"
      >
        <div class="tom-header">
          <span class="observer">{{ rel.observer }}</span>
          <span class="arrow">&rarr;</span>
          <span class="target">{{ rel.target }}</span>
        </div>

        <div class="tom-body">
          <div class="tom-field">
            <span class="field-label">信頼度</span>
            <span class="trust-bar-container">
              <span
                class="trust-bar"
                :style="{ width: rel.trustLevel * 100 + '%', background: trustColor(rel.trustLevel) }"
              ></span>
            </span>
            <span :style="{ color: trustColor(rel.trustLevel) }">{{ (rel.trustLevel * 100).toFixed(0) }}%</span>
          </div>

          <div class="tom-field">
            <span class="field-label">予測行動</span>
            <span class="predicted-action">{{ rel.predictedAction || '不明' }}</span>
          </div>

          <div v-if="rel.inferredGoals.length > 0" class="tom-field">
            <span class="field-label">推測目標</span>
            <ul class="inferred-goals">
              <li v-for="(goal, idx) in rel.inferredGoals.slice(0, 3)" :key="idx">{{ goal }}</li>
            </ul>
          </div>

          <div class="tom-field">
            <span class="field-label">確信度</span>
            <span>{{ (rel.confidence * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tom-map {
  padding: 1rem;
}
.no-data {
  text-align: center;
  color: #999;
  padding: 2rem;
}
.relation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}
.tom-card {
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  overflow: hidden;
}
.tom-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: #f8f9fa;
  font-weight: 600;
}
.arrow {
  color: #999;
}
.tom-body {
  padding: 0.75rem;
}
.tom-field {
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.field-label {
  font-size: 0.8rem;
  color: #888;
  min-width: 70px;
}
.trust-bar-container {
  flex: 1;
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}
.trust-bar {
  height: 100%;
  border-radius: 4px;
}
.predicted-action {
  font-size: 0.85rem;
}
.inferred-goals {
  list-style: none;
  padding: 0;
  margin: 0;
}
.inferred-goals li {
  font-size: 0.85rem;
  padding: 0.15rem 0;
}
</style>
