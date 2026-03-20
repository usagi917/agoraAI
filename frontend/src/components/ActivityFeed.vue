<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useActivityStore } from '../stores/activityStore'

const props = defineProps<{
  status: string
}>()

const activityStore = useActivityStore()
const scrollEl = ref<HTMLElement | null>(null)
const isHovering = ref(false)
const viewMode = ref<'log' | 'card' | 'timeline'>('timeline')

const LIVE_STATUSES = new Set(['running', 'generating_report', 'connecting'])

const levelColors: Record<string, string> = {
  info: 'var(--text-muted)',
  event: 'var(--accent)',
  phase: '#8fd8ff',
  error: 'var(--danger)',
  agent: '#FFB74D',
}

const trackLabels: Record<string, string> = {
  phase: 'Stage',
  timeline: 'Timeline',
  agent: 'Agent',
  graph: 'Graph',
  report: 'Report',
  swarm: 'Swarm',
}

const timelineEntries = computed(() => activityStore.entries.slice(-60))
const statusLabel = computed(() => (
  LIVE_STATUSES.has(props.status) ? 'LIVE' : props.status.toUpperCase()
))

function formatTime(ts: number) {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`
}

function entryTrackLabel(track?: string) {
  if (!track) return 'Event'
  return trackLabels[track] || track
}

watch(
  () => activityStore.entries.length,
  async () => {
    if (isHovering.value) return
    await nextTick()
    if (scrollEl.value) {
      scrollEl.value.scrollTop = scrollEl.value.scrollHeight
    }
  },
)
</script>

<template>
  <div class="panel-card activity-panel">
    <div class="panel-header">
      <h3>Activity</h3>
      <div class="activity-controls">
        <button
          class="mode-btn"
          :class="{ active: viewMode === 'log' }"
          @click="viewMode = 'log'"
          title="Log view"
        >≡</button>
        <button
          class="mode-btn"
          :class="{ active: viewMode === 'card' }"
          @click="viewMode = 'card'"
          title="Card view"
        >▦</button>
        <button
          class="mode-btn"
          :class="{ active: viewMode === 'timeline' }"
          @click="viewMode = 'timeline'"
          title="Timeline view"
        >⋮</button>
        <span class="panel-count" :class="{ live: LIVE_STATUSES.has(status) }">
          {{ statusLabel }}
        </span>
      </div>
    </div>
    <div
      ref="scrollEl"
      class="activity-scroll"
      @mouseenter="isHovering = true"
      @mouseleave="isHovering = false"
    >
      <template v-if="activityStore.entries.length === 0">
        <div class="activity-empty">
          <div v-if="LIVE_STATUSES.has(status)" class="console-cursor">&#9608;</div>
          <span v-else>イベント待機中...</span>
        </div>
      </template>

      <template v-else-if="viewMode === 'log'">
        <TransitionGroup name="log-slide">
          <div
            v-for="entry in activityStore.entries"
            :key="entry.id"
            class="log-line"
            :style="{ color: levelColors[entry.level] || 'var(--text-muted)' }"
          >
            <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
            <span class="log-icon">{{ entry.icon }}</span>
            <span class="log-msg">{{ entry.message }}</span>
            <span v-if="entry.detail" class="log-detail">{{ entry.detail }}</span>
          </div>
        </TransitionGroup>
      </template>

      <template v-else-if="viewMode === 'card'">
        <TransitionGroup name="log-slide">
          <div
            v-for="entry in activityStore.entries"
            :key="entry.id"
            class="action-card"
            :class="[entry.level, entry.track, entry.status]"
          >
            <div class="card-header">
              <span class="card-icon">{{ entry.icon }}</span>
              <span class="card-track">{{ entryTrackLabel(entry.track) }}</span>
              <span v-if="entry.agentName" class="card-agent">{{ entry.agentName }}</span>
              <span v-if="entry.round != null" class="card-round">R{{ entry.round }}</span>
              <span class="card-time">{{ formatTime(entry.timestamp) }}</span>
            </div>
            <div class="card-body">{{ entry.message }}</div>
            <div v-if="entry.detail" class="card-detail">{{ entry.detail }}</div>
          </div>
        </TransitionGroup>
      </template>

      <template v-else>
        <TransitionGroup name="log-slide" tag="div" class="timeline-list">
          <div
            v-for="entry in timelineEntries"
            :key="entry.id"
            class="timeline-item"
            :class="[entry.track, entry.status]"
          >
            <div class="timeline-marker">
              <span class="timeline-icon">{{ entry.icon }}</span>
            </div>
            <div class="timeline-body">
              <div class="timeline-meta">
                <span class="timeline-track">{{ entryTrackLabel(entry.track) }}</span>
                <span v-if="entry.round != null" class="timeline-round">R{{ entry.round }}</span>
                <span v-if="entry.agentName" class="timeline-agent">{{ entry.agentName }}</span>
                <span class="timeline-time">{{ formatTime(entry.timestamp) }}</span>
              </div>
              <div class="timeline-message">{{ entry.message }}</div>
              <div v-if="entry.detail" class="timeline-detail">{{ entry.detail }}</div>
            </div>
          </div>
        </TransitionGroup>
      </template>
    </div>
  </div>
</template>

<style scoped>
.activity-panel { flex: 1; min-height: 0; display: flex; flex-direction: column; }

.activity-controls {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.mode-btn {
  background: none;
  border: 1px solid transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.78rem;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  line-height: 1;
}

.mode-btn:hover { color: var(--text-primary); background: rgba(255,255,255,0.06); }
.mode-btn.active { color: var(--accent); border-color: rgba(100,100,255,0.2); background: rgba(100,100,255,0.08); }

.panel-count { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); background: rgba(255,255,255,0.04); padding: 0.1rem 0.4rem; border-radius: 4px; }
.panel-count.live { color: var(--success); background: rgba(34,197,94,0.1); }

.activity-scroll {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  line-height: 1.7;
  max-height: min(22rem, 48vh);
  overflow-y: auto;
  background: rgba(0,0,0,0.3);
  border-radius: var(--radius-sm);
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  flex: 1;
  min-height: 0;
}

.activity-empty {
  color: var(--text-muted);
  font-size: 0.72rem;
  padding: 0.5rem 0;
}

.console-cursor { color: var(--text-muted); animation: breathe 1s step-end infinite; font-size: 0.72rem; }

.log-line {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  padding: 0.1rem 0;
  white-space: nowrap;
  overflow: hidden;
}

.log-time { color: var(--text-muted); font-size: 0.65rem; flex-shrink: 0; opacity: 0.6; }
.log-icon { flex-shrink: 0; width: 1em; text-align: center; }
.log-msg { overflow: hidden; text-overflow: ellipsis; }
.log-detail { color: var(--text-muted); font-size: 0.65rem; opacity: 0.7; flex-shrink: 0; }

.action-card {
  padding: 0.45rem 0.55rem;
  margin-bottom: 0.4rem;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.05);
  border-left: 2px solid var(--text-muted);
  background: rgba(255,255,255,0.025);
}

.action-card.event,
.action-card.timeline { border-left-color: var(--accent); }
.action-card.phase { border-left-color: #8fd8ff; }
.action-card.error { border-left-color: var(--danger); }
.action-card.agent { border-left-color: #FFB74D; }
.action-card.graph { border-left-color: #58d5ba; }
.action-card.report { border-left-color: #ff9f6e; }
.action-card.swarm { border-left-color: #b798ff; }

.card-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.2rem;
  flex-wrap: wrap;
}

.card-icon { font-size: 0.7rem; }
.card-track,
.timeline-track {
  font-size: 0.58rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 0.05rem 0.3rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
}

.card-agent,
.timeline-agent { font-weight: 600; font-size: 0.68rem; color: #FFB74D; }

.card-round,
.timeline-round {
  font-size: 0.6rem;
  padding: 0 0.3rem;
  border-radius: 3px;
  background: rgba(100,100,255,0.15);
  color: var(--accent);
}

.card-time,
.timeline-time { margin-left: auto; font-size: 0.6rem; color: var(--text-muted); opacity: 0.55; }

.card-body,
.timeline-message { font-size: 0.72rem; color: var(--text-secondary); }
.card-detail,
.timeline-detail { font-size: 0.65rem; color: var(--text-muted); margin-top: 0.15rem; opacity: 0.76; white-space: pre-wrap; }

.timeline-list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  padding-left: 0.25rem;
}

.timeline-list::before {
  content: '';
  position: absolute;
  left: 0.45rem;
  top: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(180deg, rgba(255,255,255,0.16), rgba(255,255,255,0.03));
}

.timeline-item {
  position: relative;
  display: grid;
  grid-template-columns: 1.2rem minmax(0, 1fr);
  gap: 0.55rem;
}

.timeline-marker {
  position: relative;
  z-index: 1;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(20, 24, 40, 0.95);
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 0 0 4px rgba(5, 8, 16, 0.65);
}

.timeline-item.graph .timeline-marker { border-color: rgba(88, 213, 186, 0.5); color: #58d5ba; }
.timeline-item.report .timeline-marker { border-color: rgba(255, 159, 110, 0.5); color: #ff9f6e; }
.timeline-item.agent .timeline-marker { border-color: rgba(255, 183, 77, 0.5); color: #FFB74D; }
.timeline-item.swarm .timeline-marker { border-color: rgba(183, 152, 255, 0.5); color: #b798ff; }
.timeline-item.phase .timeline-marker { border-color: rgba(143, 216, 255, 0.5); color: #8fd8ff; }
.timeline-item.failed .timeline-marker { border-color: rgba(239, 68, 68, 0.55); color: var(--danger); }

.timeline-body {
  min-width: 0;
  padding: 0.15rem 0 0.45rem;
}

.timeline-meta {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.2rem;
  flex-wrap: wrap;
}

.log-slide-enter-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.log-slide-enter-from { opacity: 0; transform: translateX(8px); }
.log-slide-leave-active { display: none; }

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>
