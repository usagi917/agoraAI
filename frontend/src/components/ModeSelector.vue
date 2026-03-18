<script setup lang="ts">
import type { SimulationMode } from '../stores/simulationStore'

defineProps<{
  modelValue: SimulationMode
}>()

const emit = defineEmits<{
  'update:modelValue': [value: SimulationMode]
}>()

const modes = [
  {
    value: 'single' as SimulationMode,
    label: 'Single',
    desc: '1つの深い分析',
    detail: '高速・詳細レポート',
  },
  {
    value: 'swarm' as SimulationMode,
    label: 'Swarm',
    desc: '複数視点の群知能',
    detail: 'N Colony・確率分布',
  },
  {
    value: 'hybrid' as SimulationMode,
    label: 'Hybrid',
    desc: '深い分析 + 統計分布',
    detail: 'Deep + Shallow Colony',
  },
]
</script>

<template>
  <div class="mode-selector">
    <div
      v-for="m in modes"
      :key="m.value"
      class="mode-card"
      :class="{ selected: modelValue === m.value }"
      @click="emit('update:modelValue', m.value)"
    >
      <div class="mode-indicator" :class="{ active: modelValue === m.value }"></div>
      <div class="mode-info">
        <h4 class="mode-label">{{ m.label }}</h4>
        <p class="mode-desc">{{ m.desc }}</p>
        <span class="mode-detail">{{ m.detail }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mode-selector {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}

.mode-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem;
  cursor: pointer;
  transition: border-color 0.25s ease;
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  min-height: 100%;
}

.mode-card:hover {
  border-color: rgba(255, 255, 255, 0.12);
}

.mode-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.mode-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-muted);
  margin-top: 0.2rem;
  flex-shrink: 0;
  transition: all 0.3s;
}

.mode-indicator.active {
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent-glow);
}

.mode-label {
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin-bottom: 0.2rem;
}

.mode-desc {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-bottom: 0.4rem;
}

.mode-detail {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
}

@media (max-width: 640px) {
  .mode-selector {
    grid-template-columns: 1fr;
  }

  .mode-card {
    padding: 1rem;
  }
}
</style>
