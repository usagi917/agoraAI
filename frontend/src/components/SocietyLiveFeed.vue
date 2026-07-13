<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useSocietyGraphStore, type FeedEntry } from '../stores/societyGraphStore'
import { useSimulationStore } from '../stores/simulationStore'
import { getStanceColor } from '../constants/stances'
import { resolveAgentByName } from '../utils/agentNameResolver'

type Side = 'left' | 'right' | 'center'

interface DisplayEntry extends FeedEntry {
  side: Side
}

const BODY_LIMIT = 150
// Cap the number of nodes actually rendered; the store buffer stays at 300.
const VISIBLE_LIMIT = 150
const LIVE_STATUSES = new Set(['running', 'generating_report', 'connecting'])

const societyGraphStore = useSocietyGraphStore()
const simulationStore = useSimulationStore()
const emit = defineEmits<{
  (e: 'select-agent', agentId: string): void
  (e: 'highlight-edge', sourceId: string, targetId: string): void
}>()

const scrollEl = ref<HTMLElement | null>(null)
const autoFollow = ref(true)
const filterMode = ref<'all' | 'shifts_only'>('all')
const filterAgentId = ref<string | null>(null)

const agentOptions = computed(() => Array.from(societyGraphStore.liveAgents.values()).map((agent) => ({
  id: agent.id,
  name: agent.displayName,
})))

function resolveAgentId(name?: string): string | undefined {
  if (!name) return undefined
  return resolveAgentByName(societyGraphStore.liveAgents.values(), name)?.id
}

function selectNamedAgent(name?: string) {
  if (name) emit('select-agent', resolveAgentId(name) ?? name)
}

function highlightAddressedEdge(entry: FeedEntry) {
  const sourceId = resolveAgentId(entry.participant_name)
  const targetId = resolveAgentId(entry.addressed_to)
  if (sourceId && targetId) emit('highlight-edge', sourceId, targetId)
}

function deriveStanceClass(position?: string): string {
  if (!position) return 'stance-neutral'
  const lower = position.toLowerCase()
  if (lower.includes('賛成') || lower.includes('agree') || lower.includes('support')) return 'stance-agree'
  if (lower.includes('反対') || lower.includes('disagree') || lower.includes('oppose')) return 'stance-disagree'
  return 'stance-neutral'
}

function truncate(text: string | undefined, limit: number): string {
  if (!text) return ''
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

const displayEntries = computed<DisplayEntry[]>(() => {
  const entries = societyGraphStore.feedEntries.filter((entry) => {
    if (
      filterMode.value === 'shifts_only'
      && (entry.kind === 'dialogue' || entry.kind === 'population_voice')
    ) return false
    if (!filterAgentId.value || entry.kind === 'round') return true
    if (entry.kind === 'population_voice') return false
    const relatedName = entry.kind === 'dialogue' ? entry.participant_name : entry.participant
    return resolveAgentId(relatedName) === filterAgentId.value
  })
  let sideCount = 0
  return entries.map((entry) => {
    let side: Side = 'center'
    if (entry.kind !== 'round') {
      side = sideCount % 2 === 0 ? 'left' : 'right'
      sideCount++
    }
    return { ...entry, side }
  })
})

// Only render the tail; keeps DOM node count bounded under high-frequency streaming.
const visibleEntries = computed<DisplayEntry[]>(() =>
  displayEntries.value.length > VISIBLE_LIMIT
    ? displayEntries.value.slice(-VISIBLE_LIMIT)
    : displayEntries.value,
)

const isLive = computed(() => LIVE_STATUSES.has(simulationStore.status))
const showRipple = computed(() => isLive.value && displayEntries.value.length > 0)

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  autoFollow.value = el.scrollHeight - el.scrollTop - el.clientHeight < 48
}

function scrollToBottom(behavior: ScrollBehavior = 'smooth') {
  const el = scrollEl.value
  if (!el || typeof el.scrollTo !== 'function') return
  el.scrollTo({ top: el.scrollHeight, behavior })
}

function scrollToLatest() {
  autoFollow.value = true
  nextTick(() => scrollToBottom('smooth'))
}

// Coalesce follow-scrolls into a single animation frame. Rapid successive
// appends (or live streaming) collapse to one instant scroll to avoid the
// jank of many queued smooth animations.
let scrollRaf = 0
let coalescedSingle = true

function requestFollowScroll() {
  if (!autoFollow.value) return
  if (scrollRaf) {
    coalescedSingle = false
    return
  }
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = 0
    const behavior: ScrollBehavior = coalescedSingle && !isLive.value ? 'smooth' : 'auto'
    coalescedSingle = true
    scrollToBottom(behavior)
  })
}

watch(() => societyGraphStore.feedEntries.length, requestFollowScroll)

onBeforeUnmount(() => {
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
})
</script>

<template>
  <section class="society-live-feed">
    <div class="feed-header">
      <h3 class="feed-title">ライブフィード</h3>
      <span class="feed-status" :class="{ live: isLive }">
        {{ isLive ? 'LIVE' : 'IDLE' }}
      </span>
    </div>

    <div class="feed-filters">
      <select v-model="filterMode" class="feed-filter-select feed-filter-mode">
        <option value="all">全発言</option>
        <option value="shifts_only">スタンス変化のみ</option>
      </select>
      <select v-model="filterAgentId" class="feed-filter-select feed-filter-agent">
        <option :value="null">全員</option>
        <option v-for="agent in agentOptions" :key="agent.id" :value="agent.id">
          {{ agent.name }}
        </option>
      </select>
    </div>

    <div ref="scrollEl" class="feed-scroll" @scroll="onScroll">
      <div v-if="displayEntries.length === 0" class="feed-empty">
        議論の発言・スタンス変化を待機中...
      </div>

      <template v-else>
        <TransitionGroup name="feed-item" tag="div" class="feed-track">
          <div
            v-for="entry in visibleEntries"
            :key="entry.id"
            class="feed-item"
            :class="[entry.side, `kind-${entry.kind}`]"
          >
            <span class="feed-dot" :class="`kind-${entry.kind}`" aria-hidden="true" />

            <!-- Round marker -->
            <div v-if="entry.kind === 'round'" class="feed-round">
              <span class="feed-round-badge">Round {{ entry.round }}</span>
              <span v-if="entry.round_name" class="feed-round-name">{{ entry.round_name }}</span>
            </div>

            <!-- Stance shift -->
            <div v-else-if="entry.kind === 'stance_shift'" class="feed-card feed-stance-shift">
              <div class="shift-head">
                <span class="shift-icon" aria-hidden="true">◉</span>
                <button class="shift-participant feed-person-button" type="button" @click="selectNamedAgent(entry.participant)">
                  {{ entry.participant }}
                </button>
              </div>
              <div class="shift-transition">
                <span class="shift-chip shift-from" :style="{ '--chip-color': getStanceColor(entry.from) }">{{ entry.from }}</span>
                <span class="shift-arrow" aria-hidden="true">→</span>
                <span class="shift-chip shift-to" :style="{ '--chip-color': getStanceColor(entry.to) }">{{ entry.to }}</span>
              </div>
              <p v-if="entry.reason" class="shift-reason">{{ entry.reason }}</p>
            </div>

            <!-- Population voice -->
            <button
              v-else-if="entry.kind === 'population_voice'"
              class="feed-card feed-population-voice"
              type="button"
              :style="{ '--stance-color': getStanceColor(entry.stance) }"
              @click="entry.agent_id && emit('select-agent', entry.agent_id)"
            >
              <div class="feed-card-head">
                <span class="feed-voice-badge">市民の声</span>
                <span class="feed-voice-person">{{ [entry.age_bracket, entry.occupation].filter(Boolean).join('・') }}</span>
              </div>
              <div class="feed-voice-stance">
                <template v-if="entry.prev_stance != null">
                  <span :style="{ color: getStanceColor(entry.prev_stance) }">{{ entry.prev_stance }}</span>
                  <span aria-hidden="true">→</span>
                </template>
                <span :style="{ color: getStanceColor(entry.stance) }">{{ entry.stance }}</span>
              </div>
              <p class="feed-body">{{ truncate(entry.comment, BODY_LIMIT) }}</p>
            </button>

            <!-- Dialogue -->
            <div
              v-else-if="entry.kind === 'dialogue'"
              class="feed-card feed-dialogue"
              :class="deriveStanceClass(entry.position)"
              :style="{ '--stance-color': getStanceColor(entry.position) }"
            >
              <div class="feed-card-head">
                <button class="feed-speaker feed-person-button" type="button" @click="selectNamedAgent(entry.participant_name)">
                  {{ entry.participant_name }}
                </button>
                <button v-if="entry.addressed_to" class="feed-addressed feed-person-button" type="button" @click="highlightAddressedEdge(entry)">
                  → {{ entry.addressed_to }}
                </button>
                <span v-if="entry.position" class="feed-position">{{ entry.position }}</span>
              </div>
              <p class="feed-body">{{ truncate(entry.argument, BODY_LIMIT) }}</p>
            </div>
          </div>
        </TransitionGroup>

        <div v-if="showRipple" class="feed-ripple" aria-hidden="true">
          <span /><span /><span />
        </div>
      </template>
    </div>

    <button
      v-if="!autoFollow && displayEntries.length > 0"
      class="feed-jump"
      type="button"
      @click="scrollToLatest"
    >
      最新へ ↓
    </button>
  </section>
</template>

<style scoped>
.society-live-feed {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.feed-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.feed-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}

.feed-status {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.08em;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
}
.feed-status.live {
  color: var(--success);
  background: rgba(34, 197, 94, 0.12);
}

.feed-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.feed-filter-select {
  min-width: 8rem;
  padding: 0.3rem 0.5rem;
  color: var(--text-secondary);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
}

.feed-scroll {
  position: relative;
  max-height: 28rem;
  overflow-y: auto;
  padding: var(--space-2) 0;
}

.feed-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 8rem;
  color: var(--text-muted);
  font-size: var(--text-xs);
}

/* --- Central axis timeline --- */
.feed-track {
  position: relative;
  padding: var(--space-2) 0;
}
.feed-track::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  transform: translateX(-50%);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.03));
}

.feed-item {
  position: relative;
  width: 50%;
  box-sizing: border-box;
  padding: 0 1.75rem;
  margin-bottom: var(--space-4);
}
.feed-item.left {
  left: 0;
}
.feed-item.right {
  left: 50%;
}

/* dot pinned to the axis */
.feed-dot {
  position: absolute;
  top: 0.5rem;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--bg-elevated);
  border: 2px solid var(--accent);
  box-shadow: 0 0 0 4px rgba(var(--accent-rgb), 0.08);
  z-index: 1;
}
.feed-item.left .feed-dot {
  right: -6px;
}
.feed-item.right .feed-dot {
  left: -6px;
}
.feed-dot.kind-stance_shift {
  border-color: var(--highlight);
  box-shadow: 0 0 0 4px rgba(236, 72, 153, 0.1);
}

/* connector tick from card toward axis */
.feed-card::before {
  content: '';
  position: absolute;
  top: 0.75rem;
  width: 1.25rem;
  height: 1px;
  background: var(--border);
}
.feed-item.left .feed-card::before {
  right: -1.25rem;
}
.feed-item.right .feed-card::before {
  left: -1.25rem;
}

.feed-card {
  position: relative;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.55rem 0.7rem;
  font-size: var(--text-xs);
}

.feed-person-button {
  padding: 0;
  color: inherit;
  background: none;
  border: 0;
  font: inherit;
  cursor: pointer;
}
.feed-person-button:hover {
  text-decoration: underline;
}

/* Dialogue */
.feed-dialogue {
  border-left: 3px solid var(--stance-color, var(--accent));
}
.feed-item.right .feed-dialogue {
  border-left: 1px solid var(--border);
  border-right: 3px solid var(--stance-color, var(--accent));
}
.feed-card-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.3rem;
}
.feed-speaker {
  font-weight: 600;
  font-size: 0.72rem;
  color: var(--text-primary);
}
.feed-addressed {
  font-size: 0.62rem;
  color: var(--text-muted);
}
.feed-position {
  margin-left: auto;
  font-size: 0.58rem;
  padding: 0.05rem 0.35rem;
  border-radius: 999px;
  color: var(--stance-color, var(--text-secondary));
  border: 1px solid color-mix(in srgb, var(--stance-color, var(--border)) 40%, transparent);
}
.feed-body {
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Population voices are intentionally quieter than council dialogue. */
.feed-population-voice {
  display: block;
  width: 100%;
  text-align: left;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--bg-elevated) 72%, transparent);
  border-color: color-mix(in srgb, var(--border) 72%, transparent);
  border-left: 2px solid color-mix(in srgb, var(--stance-color, var(--border)) 55%, transparent);
  cursor: pointer;
  opacity: 0.86;
}
.feed-voice-badge {
  padding: 0.05rem 0.35rem;
  color: var(--text-muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 0.56rem;
}
.feed-voice-person,
.feed-voice-stance {
  font-size: 0.62rem;
}
.feed-voice-stance {
  display: flex;
  gap: 0.3rem;
  margin-bottom: 0.25rem;
}
.feed-population-voice .feed-body {
  font-size: 0.66rem;
}

/* Stance shift */
.feed-stance-shift {
  border-left: 3px solid var(--highlight);
}
.feed-item.right .feed-stance-shift {
  border-left: 1px solid var(--border);
  border-right: 3px solid var(--highlight);
}
.shift-head {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.3rem;
}
.shift-icon {
  color: var(--highlight);
  font-size: 0.7rem;
}
.shift-participant {
  font-weight: 600;
  font-size: 0.72rem;
  color: var(--text-primary);
}
.shift-transition {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.shift-chip {
  font-size: 0.62rem;
  padding: 0.08rem 0.4rem;
  border-radius: 999px;
  color: var(--chip-color, var(--text-secondary));
  border: 1px solid color-mix(in srgb, var(--chip-color, var(--border)) 45%, transparent);
  background: color-mix(in srgb, var(--chip-color, transparent) 12%, transparent);
}
.shift-arrow {
  color: var(--text-muted);
  font-size: 0.7rem;
}
.shift-reason {
  margin-top: 0.3rem;
  font-size: 0.62rem;
  color: var(--text-muted);
  line-height: 1.45;
}

/* Round marker (full-width, centered) */
.feed-item.center {
  width: 100%;
  left: 0;
  padding: 0;
  display: flex;
  justify-content: center;
  margin: var(--space-3) 0;
}
.feed-item.kind-round .feed-dot {
  left: 50%;
  right: auto;
  transform: translateX(-50%);
  top: 50%;
  margin-top: -5.5px;
  border-color: var(--text-secondary);
  background: var(--bg-card);
}
.feed-round {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  z-index: 1;
}
.feed-round-badge {
  font-family: var(--font-mono);
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
}
.feed-round-name {
  font-size: 0.62rem;
  color: var(--text-muted);
}

/* Ripple at the axis tail while streaming */
.feed-ripple {
  position: relative;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.feed-ripple span {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid var(--accent);
  animation: feed-ripple 1.8s ease-out infinite;
}
.feed-ripple span:nth-child(2) { animation-delay: 0.6s; }
.feed-ripple span:nth-child(3) { animation-delay: 1.2s; }

@keyframes feed-ripple {
  0% { opacity: 0.7; transform: scale(0.4); }
  100% { opacity: 0; transform: scale(2.4); }
}

/* Jump-to-latest */
.feed-jump {
  position: absolute;
  bottom: var(--space-4);
  left: 50%;
  transform: translateX(-50%);
  padding: 0.25rem 0.7rem;
  font-size: 0.62rem;
  color: var(--text-primary);
  background: var(--accent);
  border: none;
  border-radius: 999px;
  cursor: pointer;
  box-shadow: var(--shadow);
}
.feed-jump:hover {
  background: var(--accent-hover);
}

/* Enter/leave transition */
.feed-item-enter-active {
  transition: opacity 0.3s ease-out, transform 0.3s ease-out;
}
.feed-item-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.feed-item-leave-active {
  display: none;
}

/* Mobile: single column with axis on the left */
@media (max-width: 900px) {
  .feed-track::before {
    left: 0.55rem;
  }
  .feed-item,
  .feed-item.left,
  .feed-item.right,
  .feed-item.center {
    width: 100%;
    left: 0;
    padding: 0 0 0 1.75rem;
    justify-content: flex-start;
  }
  .feed-item.left .feed-dot,
  .feed-item.right .feed-dot,
  .feed-item.kind-round .feed-dot {
    left: 0;
    right: auto;
    transform: none;
    margin-top: 0;
    top: 0.5rem;
  }
  .feed-item.left .feed-card::before,
  .feed-item.right .feed-card::before {
    left: -1.2rem;
    right: auto;
  }
  .feed-item.right .feed-dialogue {
    border-left: 3px solid var(--stance-color, var(--accent));
    border-right: 1px solid var(--border);
  }
  .feed-item.right .feed-stance-shift {
    border-left: 3px solid var(--highlight);
    border-right: 1px solid var(--border);
  }
}

@media (prefers-reduced-motion: reduce) {
  .feed-ripple span {
    animation: none;
    display: none;
  }
  .feed-item-enter-active {
    transition: none;
  }
}
</style>
