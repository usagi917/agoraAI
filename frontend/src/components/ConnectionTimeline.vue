<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useSocietyGraphStore, type MeetingArgument } from '../stores/societyGraphStore'
import ConnectionMatrix from './ConnectionMatrix.vue'

const emit = defineEmits<{
  (e: 'highlight-edge', sourceId: string, targetId: string): void
}>()

const societyGraphStore = useSocietyGraphStore()
const scrollRef = ref<HTMLElement | null>(null)
const matrixExpanded = ref(false)

interface TimelineEvent {
  id: string
  sourceId: string
  targetId: string
  sourceName: string
  targetName: string
  type: 'question' | 'response' | 'general' | 'stance_shift'
  summary: string
  round: number
  timestamp: number
}

const agentsByIndex = computed(() => {
  const map = new Map<number, { id: string; name: string }>()
  for (const agent of societyGraphStore.liveAgents.values()) {
    map.set(agent.agentIndex, {
      id: agent.id,
      name: agent.displayName || agent.label,
    })
  }
  return map
})

const timelineEvents = computed<TimelineEvent[]>(() => {
  const events: TimelineEvent[] = []

  societyGraphStore.currentArguments.forEach((arg: MeetingArgument, idx: number) => {
    const source = agentsByIndex.value.get(arg.participant_index)
    if (!source) return

    const targetIndex = arg.addressed_to_participant_index
    const target = targetIndex != null ? agentsByIndex.value.get(targetIndex) : null

    if (target) {
      const hasQuestion = arg.questions_to_others && arg.questions_to_others.length > 0
      events.push({
        id: `conn-${idx}-${source.id}-${target.id}`,
        sourceId: source.id,
        targetId: target.id,
        sourceName: source.name,
        targetName: target.name,
        type: hasQuestion ? 'question' : 'response',
        summary: arg.argument.length > 80 ? arg.argument.slice(0, 77) + '...' : arg.argument,
        round: arg.round || societyGraphStore.currentRound,
        timestamp: idx,
      })
    } else {
      // General broadcast
      for (const otherAgent of societyGraphStore.liveAgents.values()) {
        if (otherAgent.agentIndex !== arg.participant_index) {
          events.push({
            id: `conn-${idx}-${source.id}-${otherAgent.id}-gen`,
            sourceId: source.id,
            targetId: otherAgent.id,
            sourceName: source.name,
            targetName: otherAgent.displayName || otherAgent.label,
            type: 'general',
            summary: arg.argument.length > 80 ? arg.argument.slice(0, 77) + '...' : arg.argument,
            round: arg.round || societyGraphStore.currentRound,
            timestamp: idx,
          })
          break // Only show first connection for broadcasts
        }
      }
    }
  })

  // Stance shift events
  societyGraphStore.pendingStanceShifts.forEach((shift, idx) => {
    const agent = societyGraphStore.liveAgents.get(shift.agentId)
    if (!agent) return
    events.push({
      id: `shift-${idx}-${shift.agentId}`,
      sourceId: shift.agentId,
      targetId: shift.agentId,
      sourceName: agent.displayName || agent.label,
      targetName: '',
      type: 'stance_shift',
      summary: `${shift.fromStance} → ${shift.toStance}`,
      round: societyGraphStore.currentRound,
      timestamp: events.length,
    })
  })

  return events
})

const typeColors: Record<string, string> = {
  question: '#00e5ff',
  response: '#ffd740',
  general: 'rgba(200, 200, 220, 0.4)',
  stance_shift: '#ef4444',
}

const typeLabels: Record<string, string> = {
  question: 'Q',
  response: 'R',
  general: 'G',
  stance_shift: 'S',
}

function handleEventClick(event: TimelineEvent) {
  if (event.type !== 'stance_shift') {
    emit('highlight-edge', event.sourceId, event.targetId)
  }
}

watch(
  () => timelineEvents.value.length,
  async () => {
    await nextTick()
    scrollRef.value?.scrollTo({
      top: scrollRef.value.scrollHeight,
      behavior: 'smooth',
    })
  },
)
</script>

<template>
  <div class="connection-timeline">
    <!-- Connection Matrix (collapsible) -->
    <div class="matrix-section">
      <button class="matrix-toggle" @click="matrixExpanded = !matrixExpanded">
        <span class="toggle-icon">{{ matrixExpanded ? '▾' : '▸' }}</span>
        Connection Matrix
        <span class="matrix-count">{{ societyGraphStore.nodeCount }} agents</span>
      </button>
      <div v-if="matrixExpanded" class="matrix-content">
        <ConnectionMatrix @highlight-edge="(s, t) => emit('highlight-edge', s, t)" />
      </div>
    </div>

    <!-- Timeline -->
    <div class="timeline-scroll" ref="scrollRef">
      <TransitionGroup name="timeline-item">
        <div
          v-for="event in timelineEvents"
          :key="event.id"
          class="timeline-event"
          :class="{ clickable: event.type !== 'stance_shift' }"
          @click="handleEventClick(event)"
        >
          <div class="event-indicator">
            <span
              class="event-type-badge"
              :style="{ background: typeColors[event.type], color: event.type === 'response' ? '#000' : '#fff' }"
            >{{ typeLabels[event.type] }}</span>
            <span class="event-round">R{{ event.round }}</span>
          </div>

          <div class="event-body">
            <div class="event-agents">
              <span class="agent-name source">{{ event.sourceName }}</span>
              <span v-if="event.type !== 'stance_shift'" class="arrow">→</span>
              <span v-if="event.type !== 'stance_shift'" class="agent-name target">{{ event.targetName }}</span>
            </div>
            <div class="event-summary">{{ event.summary }}</div>
          </div>
        </div>
      </TransitionGroup>

      <div v-if="timelineEvents.length === 0" class="timeline-empty">
        接続イベントを待機中...
      </div>
    </div>
  </div>
</template>

<style scoped>
.connection-timeline {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.matrix-section {
  border-bottom: 1px solid var(--border, rgba(255,255,255,0.08));
}

.matrix-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.6rem;
  background: none;
  border: none;
  color: var(--text-secondary, rgba(200,200,220,0.7));
  font-size: 0.7rem;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.matrix-toggle:hover {
  color: var(--text-primary, rgba(240,240,245,0.9));
}

.toggle-icon {
  font-size: 0.6rem;
  width: 0.8rem;
}

.matrix-count {
  margin-left: auto;
  font-weight: 400;
  font-size: 0.6rem;
  color: var(--text-muted, rgba(150,150,170,0.5));
  font-family: var(--font-mono, monospace);
}

.matrix-content {
  padding: 0.4rem;
  max-height: 14rem;
  overflow-y: auto;
}

.timeline-scroll {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.4rem;
}

.timeline-event {
  display: flex;
  gap: 0.5rem;
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  transition: background 0.15s;
}
.timeline-event.clickable {
  cursor: pointer;
}
.timeline-event.clickable:hover {
  background: rgba(255, 255, 255, 0.06);
}

.event-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
  flex-shrink: 0;
  width: 2rem;
}

.event-type-badge {
  width: 1.4rem;
  height: 1.4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 0.6rem;
  font-weight: 700;
}

.event-round {
  font-size: 0.55rem;
  color: var(--text-muted, rgba(150,150,170,0.5));
  font-family: var(--font-mono, monospace);
}

.event-body {
  flex: 1;
  min-width: 0;
}

.event-agents {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 0.15rem;
}

.agent-name {
  font-size: 0.68rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 6rem;
}
.agent-name.source {
  color: rgba(0, 229, 255, 0.85);
}
.agent-name.target {
  color: rgba(255, 215, 64, 0.85);
}

.arrow {
  font-size: 0.65rem;
  color: var(--text-muted, rgba(150,150,170,0.4));
  flex-shrink: 0;
}

.event-summary {
  font-size: 0.65rem;
  color: var(--text-secondary, rgba(200,200,220,0.6));
  line-height: 1.35;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.timeline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 8rem;
  color: var(--text-muted, rgba(150,150,170,0.5));
  font-size: 0.75rem;
}

.timeline-scroll::-webkit-scrollbar { width: 3px; }
.timeline-scroll::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}

/* Transitions */
.timeline-item-enter-active { transition: all 0.3s ease-out; }
.timeline-item-enter-from { opacity: 0; transform: translateX(-8px); }
.timeline-item-leave-active { transition: all 0.2s ease-in; }
.timeline-item-leave-to { opacity: 0; }
</style>
