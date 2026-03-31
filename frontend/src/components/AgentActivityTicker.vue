<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAgentVisualizationStore } from '../stores/agentVisualizationStore'
import { useSimulationStore } from '../stores/simulationStore'

const vizStore = useAgentVisualizationStore()
const simStore = useSimulationStore()
const minimized = ref(false)

const MAX_VISIBLE = 8

const visibleEvents = computed(() => vizStore.tickerEvents.slice(-MAX_VISIBLE))
const hasEvents = computed(() => vizStore.tickerEvents.length > 0)
const isRunning = computed(() => simStore.status === 'running' || simStore.status === 'generating_report')

function toggleMinimized() {
  minimized.value = !minimized.value
}
</script>

<template>
  <div
    :class="['ticker-container', { minimized, 'ticker-idle': !hasEvents }]"
    v-if="hasEvents || isRunning"
  >
    <div class="ticker-header">
      <span class="ticker-scanline" />
      <button v-if="hasEvents" class="ticker-toggle" @click="toggleMinimized">
        {{ minimized ? '▲' : '▼' }}
      </button>
    </div>

    <template v-if="hasEvents && !minimized">
      <TransitionGroup name="ticker" tag="div" class="ticker-list">
        <div
          v-for="event in visibleEvents"
          :key="event.id"
          :class="['ticker-item', `type-${event.type}`]"
        >
          <span class="ticker-icon">{{ event.icon }}</span>
          <span class="ticker-agent">{{ event.agentName }}</span>
          <span class="ticker-summary">{{ event.summary }}</span>
        </div>
      </TransitionGroup>
    </template>

    <div v-else-if="hasEvents && minimized" class="ticker-minimized-line">
      <span class="ticker-icon">{{ visibleEvents[visibleEvents.length - 1]?.icon }}</span>
      <span class="ticker-agent">{{ visibleEvents[visibleEvents.length - 1]?.agentName }}</span>
      <span class="ticker-summary">{{ visibleEvents[visibleEvents.length - 1]?.summary }}</span>
    </div>

    <div v-else class="ticker-waiting">
      <span class="ticker-waiting-dot" />
      <span class="ticker-waiting-text">エージェント活動をモニタリング中...</span>
    </div>
  </div>
</template>

<style scoped>
.ticker-container {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 12;
  background: rgba(8, 10, 22, 0.85);
  backdrop-filter: blur(10px);
  border-top: 1px solid rgba(59, 130, 246, 0.2);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  overflow: hidden;
  transition: max-height 0.3s ease;
  max-height: 18rem;
}

.ticker-container.minimized {
  max-height: 2.2rem;
}

.ticker-header {
  position: relative;
  display: flex;
  justify-content: flex-end;
  padding: 0.15rem 0.5rem;
}

.ticker-scanline {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.4), transparent);
  animation: scanline-shimmer 3s ease-in-out infinite;
}

@keyframes scanline-shimmer {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.ticker-toggle {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.6rem;
  padding: 0.1rem 0.3rem;
  line-height: 1;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.ticker-toggle:hover {
  opacity: 1;
}

.ticker-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0 0.5rem 0.4rem;
  max-height: 14rem;
  overflow-y: auto;
}

.ticker-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0.4rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  line-height: 1.3;
}

.ticker-item.type-thought {
  border-left: 2px solid var(--accent, #3b82f6);
}

.ticker-item.type-communication {
  border-left: 2px solid var(--success, #22c55e);
}

.ticker-item.type-dialogue {
  border-left: 2px solid var(--warning, #f59e0b);
}

.ticker-item.type-system {
  border-left: 2px solid rgba(148, 163, 184, 0.5);
}

.ticker-icon {
  flex-shrink: 0;
  width: 1rem;
  text-align: center;
  opacity: 0.6;
}

.type-thought .ticker-icon { color: var(--accent, #3b82f6); }
.type-communication .ticker-icon { color: var(--success, #22c55e); }
.type-dialogue .ticker-icon { color: var(--warning, #f59e0b); }
.type-system .ticker-icon { color: #94a3b8; }

.ticker-agent {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--text-primary, #e5e7eb);
  max-width: 8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ticker-summary {
  color: var(--text-muted, #9ca3af);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.ticker-minimized-line {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  line-height: 1.3;
}

.ticker-minimized-line .ticker-agent {
  max-width: 6rem;
}

.ticker-waiting {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.5rem;
}

.ticker-waiting-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent, #3b82f6);
  animation: waiting-pulse 2s ease-in-out infinite;
}

.ticker-waiting-text {
  color: var(--text-muted, #9ca3af);
  font-size: 0.7rem;
}

@keyframes waiting-pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* TransitionGroup animations */
.ticker-enter-active {
  transition: all 0.35s ease-out;
}

.ticker-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.ticker-leave-active {
  transition: all 0.2s ease-in;
}

.ticker-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.ticker-move {
  transition: transform 0.3s ease;
}
</style>
