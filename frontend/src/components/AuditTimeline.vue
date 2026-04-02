<script setup lang="ts">
import { ref, computed } from 'vue'

export interface AuditEvent {
  id: string
  agent_id: string
  agent_name: string
  event_type: string
  reasoning: string
  timestamp: string
}

const props = defineProps<{
  events: AuditEvent[]
}>()

const selectedAgentId = ref<string>('')

const agentOptions = computed(() => {
  const ids = new Set(props.events.map(e => e.agent_id))
  return Array.from(ids).sort()
})

const filteredEvents = computed(() => {
  if (!selectedAgentId.value) return props.events
  return props.events.filter(e => e.agent_id === selectedAgentId.value)
})

function badgeClass(eventType: string): string {
  switch (eventType) {
    case 'stance_change': return 'badge-warning'
    case 'argument': return 'badge-accent'
    case 'agreement': return 'badge-success'
    case 'dissent': return 'badge-danger'
    default: return 'badge-default'
  }
}

function truncate(text: string, maxLen = 120): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + '...'
}
</script>

<template>
  <div class="audit-timeline" data-testid="audit-timeline">
    <div class="timeline-header">
      <h3 class="timeline-title">Audit Timeline</h3>
      <div class="timeline-filter">
        <select
          v-model="selectedAgentId"
          class="filter-select"
          data-testid="agent-filter"
        >
          <option value="">All Agents</option>
          <option v-for="id in agentOptions" :key="id" :value="id">
            {{ id }}
          </option>
        </select>
      </div>
    </div>

    <div v-if="filteredEvents.length === 0" class="timeline-empty">
      <p class="empty-text">イベントなし</p>
    </div>

    <div v-else class="timeline-list">
      <div
        v-for="event in filteredEvents"
        :key="event.id"
        class="timeline-item"
        data-testid="timeline-item"
      >
        <div class="timeline-marker">
          <span class="marker-dot" />
          <span class="marker-line" />
        </div>
        <div class="timeline-content">
          <div class="timeline-meta">
            <span class="agent-name">{{ event.agent_name }}</span>
            <span class="event-badge" :class="badgeClass(event.event_type)">
              {{ event.event_type }}
            </span>
            <span v-if="event.timestamp" class="event-time">
              {{ event.timestamp }}
            </span>
          </div>
          <p class="timeline-reasoning">{{ truncate(event.reasoning) }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.audit-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}

.timeline-title {
  font-size: var(--text-lg);
  font-weight: 700;
}

.filter-select {
  background: var(--bg-elevated);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-sm);
  font-family: var(--font-sans);
  cursor: pointer;
  min-width: 140px;
}

.filter-select:focus {
  outline: none;
  border-color: var(--border-active);
}

.timeline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80px;
}

.empty-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
}

.timeline-list {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  gap: var(--space-4);
  animation: fade-in 0.4s ease-out;
}

.timeline-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 20px;
}

.marker-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg-primary);
  box-shadow: 0 0 0 2px var(--accent-glow);
  flex-shrink: 0;
}

.marker-line {
  flex: 1;
  width: 2px;
  background: var(--border);
  min-height: 24px;
}

.timeline-item:last-child .marker-line {
  display: none;
}

.timeline-content {
  flex: 1;
  padding-bottom: var(--space-4);
}

.timeline-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-2);
}

.agent-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
}

.event-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--space-1) var(--space-2);
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: 600;
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}

.badge-accent {
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent);
}

.badge-success {
  background: rgba(34, 197, 94, 0.15);
  color: var(--success);
}

.badge-warning {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}

.badge-danger {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger);
}

.badge-default {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
}

.event-time {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.timeline-reasoning {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0;
}

@media (max-width: 640px) {
  .timeline-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }

  .filter-select {
    width: 100%;
  }
}
</style>
