<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useSocietyGraphStore } from '../stores/societyGraphStore'
import { useTheaterStore } from '../stores/theaterStore'

const emit = defineEmits<{
  (e: 'select-agent', agentId: string): void
  (e: 'highlight-edge', sourceId: string, targetId: string): void
}>()

const societyGraphStore = useSocietyGraphStore()
const theaterStore = useTheaterStore()

type FilterMode = 'all' | 'shifts_only'
const filterMode = ref<FilterMode>('all')
const filterAgentId = ref<string | null>(null)

// Track when the current meeting round started so we can exclude historical shifts
const currentRoundStartTime = ref<number>(Date.now())
watch(() => societyGraphStore.currentRound, () => {
  currentRoundStartTime.value = Date.now()
}, { immediate: true })

// Track arrival timestamps for arguments (they have no server-side timestamp)
const argTimestamps = ref<number[]>([])
watch(
  () => societyGraphStore.currentArguments.length,
  (newLen, oldLen) => {
    if (newLen === 0 || newLen < (oldLen ?? 0)) {
      argTimestamps.value = []
      return
    }
    const now = Date.now()
    while (argTimestamps.value.length < newLen) {
      argTimestamps.value.push(now)
    }
  },
  { immediate: true },
)

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

const agentOptions = computed(() => {
  const agents: { id: string; name: string }[] = []
  for (const agent of societyGraphStore.liveAgents.values()) {
    agents.push({ id: agent.id, name: agent.displayName || agent.label })
  }
  return agents.sort((a, b) => a.name.localeCompare(b.name))
})

function resolveAgent(rawId: string): { id: string; name: string } | null {
  const byId = societyGraphStore.liveAgents.get(rawId)
  if (byId) return { id: rawId, name: byId.displayName || byId.label }
  const idx = Number(rawId)
  if (Number.isInteger(idx) && idx >= 0) {
    return agentsByIndex.value.get(idx) ?? null
  }
  return null
}

type TimelineItem = ArgumentItem | ShiftItem

interface ArgumentItem {
  kind: 'argument'
  id: string
  agentId: string
  agentName: string
  targetId: string | null
  targetName: string | null
  text: string
  round: number
  sortKey: number
}

interface ShiftItem {
  kind: 'shift'
  id: string
  agentId: string
  agentName: string
  fromStance: string
  toStance: string
  reason: string
  sortKey: number
}

const argumentItems = computed<ArgumentItem[]>(() =>
  societyGraphStore.currentArguments.map((arg, idx) => {
    const source = agentsByIndex.value.get(arg.participant_index)
    const targetIdx = arg.addressed_to_participant_index
    const target = targetIdx != null ? agentsByIndex.value.get(targetIdx) : null
    return {
      kind: 'argument',
      id: `arg-${idx}`,
      agentId: source?.id ?? String(arg.participant_index),
      agentName: source?.name ?? arg.participant_name,
      targetId: target?.id ?? null,
      targetName: target?.name ?? null,
      text: arg.argument,
      round: arg.round ?? societyGraphStore.currentRound,
      // Use arrival timestamp (ms) for chronological merge with shifts
      sortKey: argTimestamps.value[idx] ?? 0,
    }
  }),
)

const shiftItems = computed<ShiftItem[]>(() =>
  // Only show shifts that belong to the current round (exclude historical accumulation)
  theaterStore.stanceShifts
    .filter(shift => shift.timestamp >= currentRoundStartTime.value)
    .map((shift, idx) => {
      const resolved = resolveAgent(shift.agentId)
      return {
        kind: 'shift',
        id: `shift-${idx}`,
        agentId: resolved?.id ?? shift.agentId,
        agentName: resolved?.name ?? shift.agentId,
        fromStance: shift.fromStance,
        toStance: shift.toStance,
        reason: shift.reason,
        // Use shift.timestamp (ms) — same scale as argTimestamps for chronological sort
        sortKey: shift.timestamp,
      }
    }),
)

const filteredItems = computed<TimelineItem[]>(() => {
  const args: TimelineItem[] = filterMode.value === 'shifts_only' ? [] : argumentItems.value
  const shifts: TimelineItem[] = shiftItems.value
  let merged = [...args, ...shifts].sort((a, b) => a.sortKey - b.sortKey)
  if (filterAgentId.value) {
    merged = merged.filter(item => item.agentId === filterAgentId.value)
  }
  return merged
})

// Fix: choose the banner entry by recency (timestamp), not by event type.
// Previously latestShift always won over latestClaim regardless of arrival order.
type BannerEvent =
  | { kind: 'shift'; agentId: string; fromStance: string; toStance: string; timestamp: number }
  | { kind: 'claim'; agentId: string; stance: string; timestamp: number }

const latestBannerEvent = computed<BannerEvent | null>(() => {
  const shift = theaterStore.latestShift
  const claim = theaterStore.latestClaim
  if (!shift && !claim) return null
  if (!shift) return { kind: 'claim', agentId: claim!.agentId, stance: claim!.stance, timestamp: claim!.timestamp }
  if (!claim) return { kind: 'shift', agentId: shift.agentId, fromStance: shift.fromStance, toStance: shift.toStance, timestamp: shift.timestamp }
  return shift.timestamp >= claim.timestamp
    ? { kind: 'shift', agentId: shift.agentId, fromStance: shift.fromStance, toStance: shift.toStance, timestamp: shift.timestamp }
    : { kind: 'claim', agentId: claim.agentId, stance: claim.stance, timestamp: claim.timestamp }
})

const stanceColor: Record<string, string> = {
  '賛成': 'var(--success)',
  '条件付き賛成': '#86efac',
  '中立': 'var(--text-muted)',
  '条件付き反対': '#fca5a5',
  '反対': 'var(--danger)',
}

function getStanceColor(stance: string): string {
  return stanceColor[stance] ?? 'var(--text-secondary)'
}
</script>

<template>
  <div class="conversations-tab">
    <!-- Latest event banner (most recent by timestamp, regardless of type) -->
    <div v-if="latestBannerEvent" class="conv-latest">
      <div class="conv-latest-item">
        <span class="conv-latest-label">{{ latestBannerEvent.kind === 'shift' ? '最新変化' : '最新主張' }}</span>
        <button
          class="conv-agent-btn"
          @click="emit('select-agent', resolveAgent(latestBannerEvent.agentId)?.id ?? latestBannerEvent.agentId)"
        >{{ resolveAgent(latestBannerEvent.agentId)?.name ?? latestBannerEvent.agentId }}</button>
        <template v-if="latestBannerEvent.kind === 'shift'">
          <span class="stance-badge" :style="{ color: getStanceColor(latestBannerEvent.fromStance) }">{{ latestBannerEvent.fromStance }}</span>
          <span class="stance-arrow">→</span>
          <span class="stance-badge" :style="{ color: getStanceColor(latestBannerEvent.toStance) }">{{ latestBannerEvent.toStance }}</span>
        </template>
        <template v-else>
          <span class="stance-badge" :style="{ color: getStanceColor(latestBannerEvent.stance) }">{{ latestBannerEvent.stance }}</span>
        </template>
      </div>
    </div>

    <!-- Filters -->
    <div class="conv-filters">
      <select class="conv-filter-select" v-model="filterMode">
        <option value="all">全発言</option>
        <option value="shifts_only">スタンス変化のみ</option>
      </select>
      <select class="conv-filter-select" v-model="filterAgentId">
        <option :value="null">全員</option>
        <option v-for="agent in agentOptions" :key="agent.id" :value="agent.id">
          {{ agent.name }}
        </option>
      </select>
    </div>

    <!-- Empty state -->
    <div v-if="filteredItems.length === 0" class="conv-empty">
      <span class="conv-empty-icon">◌</span>
      <span class="conv-empty-text">会話開始を待機中</span>
    </div>

    <!-- Timeline -->
    <div v-else class="conv-timeline">
      <template v-for="item in filteredItems" :key="item.id">
        <!-- Argument bubble -->
        <div v-if="item.kind === 'argument'" class="conv-item conv-argument">
          <div class="conv-item-header">
            <button class="conv-agent-btn" @click="emit('select-agent', item.agentId)">
              {{ item.agentName }}
            </button>
            <template v-if="item.targetName && item.targetId">
              <!-- Clicking the edge arrow highlights the relationship on the graph -->
              <button
                class="conv-edge-btn"
                :title="`グラフで ${item.agentName} → ${item.targetName} の関係を強調`"
                @click="emit('highlight-edge', item.agentId, item.targetId)"
              >→</button>
              <button class="conv-agent-btn secondary" @click="emit('select-agent', item.targetId)">
                {{ item.targetName }}
              </button>
            </template>
            <span v-else class="conv-to-arrow-static">→</span>
            <span class="conv-round-badge">R{{ item.round }}</span>
          </div>
          <p class="conv-item-text">
            {{ item.text.length > 140 ? item.text.slice(0, 137) + '…' : item.text }}
          </p>
        </div>

        <!-- Stance shift pill -->
        <div v-else class="conv-item conv-shift">
          <button class="conv-agent-btn" @click="emit('select-agent', item.agentId)">
            {{ item.agentName }}
          </button>
          <span class="conv-shift-change">
            <span class="stance-badge" :style="{ color: getStanceColor(item.fromStance) }">{{ item.fromStance }}</span>
            <span class="stance-arrow">→</span>
            <span class="stance-badge" :style="{ color: getStanceColor(item.toStance) }">{{ item.toStance }}</span>
          </span>
          <p v-if="item.reason" class="conv-shift-reason">{{ item.reason }}</p>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.conversations-tab {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  min-height: 0;
}

.conv-latest {
  padding: 0.5rem 0.75rem;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-sm);
}

.conv-latest-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  font-size: 0.78rem;
}

.conv-latest-label {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  text-transform: uppercase;
  color: var(--text-muted);
  letter-spacing: 0.06em;
}

.conv-filters {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.conv-filter-select {
  flex: 1;
  min-width: 7rem;
  padding: 0.3rem 0.5rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
}

.conv-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 1rem;
  color: var(--text-muted);
  font-size: 0.82rem;
}

.conv-empty-icon { font-size: 1.4rem; opacity: 0.5; }

.conv-timeline {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
  max-height: 28rem;
  padding-right: 0.2rem;
}

.conv-item {
  padding: 0.55rem 0.7rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}

.conv-argument { border-left: 2px solid var(--accent); }
.conv-shift { border-left: 2px solid var(--success); background: rgba(34, 197, 94, 0.04); }

.conv-item-header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
  margin-bottom: 0.35rem;
}

.conv-agent-btn {
  padding: 0.15rem 0.45rem;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: var(--radius-sm);
  color: var(--accent);
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  line-height: 1.4;
}

.conv-agent-btn:hover { background: rgba(99, 102, 241, 0.22); }
.conv-agent-btn.secondary { background: rgba(255, 255, 255, 0.06); border-color: var(--border); color: var(--text-secondary); }
.conv-agent-btn.secondary:hover { background: rgba(255, 255, 255, 0.1); }

.conv-to-arrow { color: var(--text-muted); font-size: 0.7rem; }
.conv-to-arrow-static { color: var(--text-muted); font-size: 0.7rem; }

.conv-edge-btn {
  padding: 0.1rem 0.3rem;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  font-size: 0.7rem;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.conv-edge-btn:hover {
  background: rgba(99, 102, 241, 0.12);
  color: var(--accent);
  border-color: rgba(99, 102, 241, 0.4);
}

.conv-round-badge {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  padding: 0.1rem 0.35rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}

.conv-item-text {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.55;
  color: var(--text-secondary);
}

.conv-shift-change {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.78rem;
}

.stance-badge { font-weight: 600; font-size: 0.75rem; }
.stance-arrow { color: var(--text-muted); font-size: 0.7rem; }

.conv-shift-reason {
  margin: 0.35rem 0 0;
  font-size: 0.76rem;
  color: var(--text-muted);
  line-height: 1.5;
  font-style: italic;
}
</style>
