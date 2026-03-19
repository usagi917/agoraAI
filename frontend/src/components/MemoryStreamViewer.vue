<script setup lang="ts">
import { computed } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

const store = useCognitiveStore()

const memories = computed(() => store.selectedAgentMemories)
const reflections = computed(() => store.selectedAgentReflections)

const sortedMemories = computed(() =>
  [...memories.value].sort((a, b) => b.round - a.round),
)

function importanceColor(importance: number): string {
  if (importance >= 0.8) return '#e74c3c'
  if (importance >= 0.5) return '#f39c12'
  return '#3498db'
}

function memoryTypeLabel(type: string): string {
  switch (type) {
    case 'episodic': return 'EP'
    case 'semantic': return 'SM'
    case 'procedural': return 'PR'
    default: return type
  }
}
</script>

<template>
  <div class="memory-stream-viewer">
    <div v-if="!store.selectedAgentId" class="no-selection">
      エージェントを選択してください
    </div>

    <div v-else>
      <h3>記憶ストリーム</h3>

      <!-- タイムライン -->
      <div class="timeline">
        <div
          v-for="memory in sortedMemories"
          :key="memory.id"
          class="memory-entry"
          :class="{ reflection: memory.isReflection }"
        >
          <div class="memory-meta">
            <span class="round-badge">R{{ memory.round }}</span>
            <span
              class="type-badge"
              :style="{ background: memory.isReflection ? '#9b59b6' : '#3498db' }"
            >
              {{ memory.isReflection ? `REF-L${memory.reflectionLevel}` : memoryTypeLabel(memory.memoryType) }}
            </span>
            <span
              class="importance-dot"
              :style="{ background: importanceColor(memory.importance) }"
              :title="`重要度: ${(memory.importance * 100).toFixed(0)}%`"
            ></span>
          </div>
          <div class="memory-content">{{ memory.content }}</div>
        </div>
      </div>

      <!-- Reflection 階層 -->
      <div v-if="reflections.length > 0" class="reflection-section">
        <h4>洞察 (Reflections)</h4>
        <div v-for="(r, idx) in reflections" :key="idx" class="reflection-entry">
          <div class="reflection-level">Level {{ r.level }}</div>
          <div class="reflection-insight">{{ r.insight }}</div>
          <div class="reflection-importance">重要度: {{ (r.importance * 100).toFixed(0) }}%</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.memory-stream-viewer {
  height: 100%;
  overflow-y: auto;
}
.no-selection {
  padding: 2rem;
  text-align: center;
  color: var(--text-muted);
}
.timeline {
  position: relative;
  padding-left: 1rem;
  border-left: 2px solid var(--border);
}
.memory-entry {
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  margin-left: 1rem;
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--border);
  position: relative;
  transition: border-color 0.2s;
}
.memory-entry:hover {
  border-color: rgba(255,255,255,0.1);
}
.memory-entry::before {
  content: '';
  position: absolute;
  left: -1.4rem;
  top: 1rem;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent-glow, rgba(99,102,241,0.4));
}
.memory-entry.reflection {
  background: rgba(155,89,182,0.08);
  border-left: 3px solid #9b59b6;
}
.memory-entry.reflection::before {
  background: #9b59b6;
  box-shadow: 0 0 6px rgba(155,89,182,0.4);
}
.memory-meta {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.4rem;
}
.round-badge {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-muted);
  font-weight: 600;
}
.type-badge {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: white;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
}
.importance-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.memory-content {
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--text-secondary);
}
.reflection-section {
  margin-top: 2rem;
}
.reflection-section h4 {
  font-size: 0.85rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
  color: var(--text-primary);
}
.reflection-entry {
  padding: 0.75rem;
  margin-bottom: 0.5rem;
  background: rgba(155,89,182,0.08);
  border-radius: var(--radius-sm);
  border-left: 3px solid #9b59b6;
  border: 1px solid rgba(155,89,182,0.2);
  border-left: 3px solid #9b59b6;
}
.reflection-level {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: #9b59b6;
  font-weight: 600;
}
.reflection-insight {
  margin-top: 0.25rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.reflection-importance {
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}
</style>
