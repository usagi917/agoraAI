<script setup lang="ts">
import { computed } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

const store = useCognitiveStore()

const relations = computed(() => store.tomRelations)

function trustColor(trust: number): string {
  if (trust >= 0.7) return 'var(--success)'
  if (trust >= 0.4) return 'var(--warning)'
  return 'var(--danger)'
}

function trustGlow(trust: number): string {
  if (trust >= 0.7) return 'var(--success-glow)'
  if (trust >= 0.4) return 'var(--warning-glow)'
  return 'var(--danger-glow)'
}
</script>

<template>
  <div class="tom-map">
    <h3>Theory of Mind マップ</h3>

    <div v-if="relations.length === 0" class="no-data">
      <div class="no-data-icon">&#x1f50d;</div>
      <p>ToMデータがまだありません。</p>
      <p class="no-data-hint">シミュレーションを実行すると、エージェント間の心の理論モデルがここに表示されます。</p>
    </div>

    <div v-else class="relation-grid">
      <div
        v-for="rel in relations"
        :key="`${rel.observer}-${rel.target}`"
        class="tom-card"
      >
        <div class="tom-header">
          <span class="observer">{{ rel.observer }}</span>
          <span class="arrow-indicator">
            <span class="arrow-line"></span>
            <span class="arrow-head"></span>
          </span>
          <span class="target">{{ rel.target }}</span>
        </div>

        <div class="tom-body">
          <div class="tom-field">
            <span class="field-label">信頼度</span>
            <span class="trust-bar-container">
              <span
                class="trust-bar"
                :style="{ width: rel.trustLevel * 100 + '%', background: trustColor(rel.trustLevel), boxShadow: '0 0 6px ' + trustGlow(rel.trustLevel) }"
              ></span>
            </span>
            <span class="trust-value" :style="{ color: trustColor(rel.trustLevel) }">{{ (rel.trustLevel * 100).toFixed(0) }}%</span>
          </div>

          <div class="tom-field">
            <span class="field-label">予測行動</span>
            <span class="predicted-action">{{ rel.predictedAction || '不明' }}</span>
          </div>

          <div v-if="rel.inferredGoals.length > 0" class="tom-field tom-field-goals">
            <span class="field-label">推測目標</span>
            <ul class="inferred-goals">
              <li v-for="(goal, idx) in rel.inferredGoals.slice(0, 3)" :key="idx">{{ goal }}</li>
            </ul>
          </div>

          <div class="tom-field">
            <span class="field-label">確信度</span>
            <span class="confidence-text">{{ (rel.confidence * 100).toFixed(0) }}%</span>
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
.tom-map h3 {
  color: var(--text-primary);
  margin-bottom: 1rem;
}

/* Empty state */
.no-data {
  text-align: center;
  color: var(--text-muted);
  padding: 3rem 1.5rem;
  background: var(--bg-card);
  border: 1px dashed var(--border);
  border-radius: var(--radius-lg);
}
.no-data-icon {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  opacity: 0.5;
}
.no-data p {
  margin: 0.25rem 0;
}
.no-data-hint {
  font-size: 0.82rem;
  color: var(--text-muted);
}

/* Grid */
.relation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

/* Card */
.tom-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg-card);
  transition: border-color 0.2s;
}
.tom-card:hover {
  border-color: var(--border-active);
}

/* Header with dark bg */
.tom-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: var(--bg-surface);
  font-weight: 600;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border);
}
.observer {
  color: var(--accent);
}
.target {
  color: var(--text-primary);
}

/* CSS arrow indicator */
.arrow-indicator {
  display: flex;
  align-items: center;
  gap: 0;
  margin: 0 0.25rem;
}
.arrow-line {
  display: block;
  width: 20px;
  height: 2px;
  background: var(--text-muted);
}
.arrow-head {
  display: block;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 7px solid var(--text-muted);
}

/* Body */
.tom-body {
  padding: 0.75rem 1rem;
}
.tom-field {
  margin-bottom: 0.6rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.tom-field-goals {
  align-items: flex-start;
}
.field-label {
  font-size: 0.8rem;
  color: var(--text-muted);
  min-width: 70px;
  flex-shrink: 0;
}

/* Trust bar */
.trust-bar-container {
  flex: 1;
  height: 8px;
  background: var(--border);
  border-radius: 4px;
  overflow: hidden;
}
.trust-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 0.5s ease;
}
.trust-value {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  min-width: 36px;
  text-align: right;
}

.predicted-action {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.confidence-text {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.inferred-goals {
  list-style: none;
  padding: 0;
  margin: 0;
}
.inferred-goals li {
  font-size: 0.85rem;
  color: var(--text-secondary);
  padding: 0.15rem 0;
  padding-left: 0.75rem;
  position: relative;
}
.inferred-goals li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent);
  transform: translateY(-50%);
}
</style>
