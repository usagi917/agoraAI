<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, toRef } from 'vue'
import { useAgentStory } from '../composables/useAgentStory'
import { useSocietyGraphStore, STANCE_COLORS } from '../stores/societyGraphStore'

const props = defineProps<{
  simulationId: string
  agentId: string | null
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const societyGraphStore = useSocietyGraphStore()
const agentIdRef = toRef(props, 'agentId')
const { agentDetail, opinionJourney, influenceMap, loading, error } = useAgentStory(
  props.simulationId,
  agentIdRef,
)

const activeTab = ref<'journey' | 'profile'>('journey')

// Reset to journey tab when agent changes
watch(agentIdRef, () => {
  activeTab.value = 'journey'
})

// Agent name: prefer API data, fallback to store
const agentInStore = computed(() =>
  props.agentId ? societyGraphStore.liveAgents.get(props.agentId) ?? null : null,
)

const displayName = computed(() => {
  return (
    agentDetail.value?.meeting_participant?.display_name
    ?? agentInStore.value?.displayName
    ?? agentInStore.value?.label
    ?? props.agentId
    ?? ''
  )
})

const currentStance = computed(() => {
  return (
    agentInStore.value?.stance
    ?? agentDetail.value?.meeting_participant?.stance
    ?? null
  )
})

const stanceColor = computed(() =>
  currentStance.value ? (STANCE_COLORS[currentStance.value] ?? 'var(--text-secondary)') : 'var(--text-muted)',
)

const demographics = computed(() => {
  const d = agentDetail.value?.demographics
  if (!d) return agentInStore.value ? `${agentInStore.value.age}歳 / ${agentInStore.value.occupation} / ${agentInStore.value.region}` : ''
  return `${d.age}歳 / ${d.occupation} / ${d.region}`
})

const bigFiveEntries = computed(() => {
  const bf = agentDetail.value?.big_five
  if (!bf) return []
  const labels: Record<string, string> = {
    openness: '開放性',
    conscientiousness: '誠実性',
    extraversion: '外向性',
    agreeableness: '協調性',
    neuroticism: '神経質性',
  }
  return Object.entries(bf).map(([key, val]) => ({
    label: labels[key] ?? key,
    value: typeof val === 'number' ? val : 0,
  }))
})

const valuesEntries = computed(() => {
  const v = agentDetail.value?.values
  if (!v) return []
  return Object.entries(v)
    .filter(([, val]) => val != null)
    .slice(0, 6)
    .map(([key, val]) => ({ key, val: String(val) }))
})

function handleEscape(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) {
    emit('close')
  }
}

onMounted(() => window.addEventListener('keydown', handleEscape))
onUnmounted(() => window.removeEventListener('keydown', handleEscape))
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer-fade">
      <div v-if="open" class="drawer-backdrop" @click.self="$emit('close')" />
    </Transition>
    <Transition name="drawer-slide">
      <div
        v-if="open"
        role="dialog"
        aria-modal="true"
        :aria-label="`${displayName} のストーリー`"
        class="agent-story-drawer"
      >
        <!-- Header -->
        <div class="drawer-header">
          <div class="drawer-agent-info">
            <h2 class="drawer-agent-name">{{ displayName }}</h2>
            <p class="drawer-demographics">{{ demographics }}</p>
          </div>
          <button class="drawer-close-btn" @click="$emit('close')" aria-label="閉じる">
            &times;
          </button>
        </div>

        <!-- Stance badge -->
        <div v-if="currentStance" class="drawer-stance-badge" :style="{ color: stanceColor, borderColor: stanceColor }">
          {{ currentStance }}
        </div>

        <!-- Tabs -->
        <div class="drawer-tabs" role="tablist">
          <button
            role="tab"
            :aria-selected="activeTab === 'journey'"
            class="drawer-tab"
            :class="{ active: activeTab === 'journey' }"
            @click="activeTab = 'journey'"
          >
            意見の軌跡
          </button>
          <button
            role="tab"
            :aria-selected="activeTab === 'profile'"
            class="drawer-tab"
            :class="{ active: activeTab === 'profile' }"
            @click="activeTab = 'profile'"
          >
            プロフィール
          </button>
        </div>

        <!-- Content -->
        <div class="drawer-content">
          <!-- Loading -->
          <div v-if="loading" class="drawer-loading">
            <div class="loading-dots"><span /><span /><span /></div>
            <span>データを取得中...</span>
          </div>

          <!-- Error -->
          <div v-else-if="error" class="drawer-error">
            {{ error }}
          </div>

          <!-- Journey tab -->
          <div v-else-if="activeTab === 'journey'" class="journey-tab">
            <div v-if="influenceMap.length > 0" class="influence-section">
              <h4 class="section-label">よく話しかけた相手</h4>
              <div class="influence-list">
                <div
                  v-for="entry in influenceMap"
                  :key="entry.agentName"
                  class="influence-item"
                >
                  <span class="influence-name">{{ entry.agentName }}</span>
                  <span class="influence-count">{{ entry.count }}回</span>
                </div>
              </div>
            </div>

            <h4 class="section-label">発言の流れ</h4>
            <div v-if="opinionJourney.length === 0" class="journey-empty">
              まだ発言データがありません
            </div>
            <div v-else class="journey-timeline">
              <div
                v-for="(item, idx) in opinionJourney"
                :key="idx"
                class="journey-item"
                :class="item.type"
              >
                <div class="journey-marker">
                  <span class="journey-round">R{{ item.round }}</span>
                  <div class="journey-line" v-if="idx < opinionJourney.length - 1" />
                </div>
                <div class="journey-body">
                  <div v-if="item.type === 'stance_shift'" class="shift-banner">
                    <span class="shift-belief-label">信念更新</span>
                  </div>
                  <p class="journey-content">{{ item.content }}</p>
                  <span v-if="item.addressedTo" class="journey-addressed">→ {{ item.addressedTo }}</span>
                  <span v-if="item.roundName" class="journey-round-name">{{ item.roundName }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Profile tab -->
          <div v-else-if="activeTab === 'profile'" class="profile-tab">
            <!-- Big Five -->
            <div v-if="bigFiveEntries.length > 0" class="profile-section">
              <h4 class="section-label">Big Five パーソナリティ</h4>
              <div class="bigfive-list">
                <div
                  v-for="entry in bigFiveEntries"
                  :key="entry.label"
                  class="bigfive-item"
                >
                  <span class="bigfive-label">{{ entry.label }}</span>
                  <div class="bigfive-track">
                    <div
                      class="bigfive-fill"
                      :style="{ width: `${Math.round(entry.value * 100)}%` }"
                    />
                  </div>
                  <span class="bigfive-val">{{ Math.round(entry.value * 100) }}</span>
                </div>
              </div>
            </div>

            <!-- Values -->
            <div v-if="valuesEntries.length > 0" class="profile-section">
              <h4 class="section-label">価値観</h4>
              <div class="values-grid">
                <div v-for="entry in valuesEntries" :key="entry.key" class="values-item">
                  <span class="values-key">{{ entry.key }}</span>
                  <span class="values-val">{{ entry.val }}</span>
                </div>
              </div>
            </div>

            <!-- Life context -->
            <div v-if="agentDetail?.life_event || agentDetail?.local_context" class="profile-section">
              <h4 class="section-label">生活背景</h4>
              <p v-if="agentDetail.life_event" class="profile-text">{{ agentDetail.life_event }}</p>
              <p v-if="agentDetail.local_context" class="profile-text muted">{{ agentDetail.local_context }}</p>
            </div>

            <!-- Connections count -->
            <div v-if="agentDetail?.connections?.length" class="profile-section">
              <h4 class="section-label">社会的接続</h4>
              <p class="profile-text">{{ agentDetail.connections.length }} 件の接続</p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 200;
}

.agent-story-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: min(28rem, 100vw);
  height: 100dvh;
  background: var(--bg-panel, #0d0f1e);
  border-left: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  display: flex;
  flex-direction: column;
  z-index: 201;
  overflow: hidden;
}

/* Transitions */
.drawer-fade-enter-active,
.drawer-fade-leave-active { transition: opacity 0.22s ease; }
.drawer-fade-enter-from,
.drawer-fade-leave-to { opacity: 0; }

.drawer-slide-enter-active,
.drawer-slide-leave-active { transition: transform 0.26s cubic-bezier(0.4, 0, 0.2, 1); }
.drawer-slide-enter-from,
.drawer-slide-leave-to { transform: translateX(100%); }

/* Header */
.drawer-header {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 1rem 1rem 0.75rem;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.06));
}

.drawer-agent-info {
  flex: 1;
  min-width: 0;
}

.drawer-agent-name {
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0 0 0.2rem;
}

.drawer-demographics {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin: 0;
}

.drawer-close-btn {
  flex-shrink: 0;
  width: 1.8rem;
  height: 1.8rem;
  background: none;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.1));
  border-radius: 50%;
  color: var(--text-secondary);
  font-size: 1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, color 0.15s;
}
.drawer-close-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
}

/* Stance badge */
.drawer-stance-badge {
  display: inline-block;
  margin: 0.5rem 1rem 0;
  padding: 0.2rem 0.6rem;
  border: 1px solid;
  border-radius: 99px;
  font-size: 0.7rem;
  font-weight: 600;
}

/* Tabs */
.drawer-tabs {
  display: flex;
  gap: 0;
  padding: 0.5rem 1rem 0;
  border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.06));
}

.drawer-tab {
  padding: 0.4rem 0.75rem;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.drawer-tab:hover { color: var(--text-secondary); }
.drawer-tab.active {
  color: var(--accent, #3b82f6);
  border-bottom-color: var(--accent, #3b82f6);
}

/* Content */
.drawer-content {
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.drawer-content::-webkit-scrollbar { width: 3px; }
.drawer-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
}

/* Loading / Error */
.drawer-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2rem 0;
  color: var(--text-muted);
  font-size: 0.78rem;
}

.drawer-error {
  padding: 0.75rem;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius-sm, 4px);
  color: var(--danger, #ef4444);
  font-size: 0.78rem;
}

/* Section label */
.section-label {
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-muted);
  margin: 0 0 0.4rem;
}

/* Influence section */
.influence-section {
  margin-bottom: 0.25rem;
}

.influence-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
}

.influence-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.5rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.06));
  border-radius: 99px;
  font-size: 0.68rem;
}

.influence-name { color: var(--text-secondary); }
.influence-count {
  font-family: var(--font-mono);
  color: var(--accent, #3b82f6);
  font-size: 0.62rem;
}

/* Journey timeline */
.journey-empty {
  color: var(--text-muted);
  font-size: 0.75rem;
  text-align: center;
  padding: 1.5rem 0;
}

.journey-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.journey-item {
  display: flex;
  gap: 0.6rem;
}

.journey-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 2.2rem;
}

.journey-round {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  color: var(--text-muted);
  padding: 0.15rem 0.3rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.06));
  border-radius: 3px;
  white-space: nowrap;
}

.journey-line {
  flex: 1;
  width: 1px;
  background: var(--border, rgba(255, 255, 255, 0.06));
  margin: 0.2rem 0;
  min-height: 0.5rem;
}

.journey-body {
  flex: 1;
  min-width: 0;
  padding-bottom: 0.75rem;
}

.shift-banner {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.5rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  color: #ef4444;
  margin-bottom: 0.3rem;
}

.shift-belief-label { color: rgba(255, 215, 64, 0.85); }

.journey-content {
  font-size: 0.73rem;
  color: var(--text-secondary);
  line-height: 1.55;
  margin: 0 0 0.25rem;
}

.journey-addressed {
  font-size: 0.62rem;
  color: var(--accent, #3b82f6);
  font-family: var(--font-mono);
}

.journey-round-name {
  font-size: 0.6rem;
  color: var(--text-muted);
  margin-left: 0.4rem;
}

/* Profile tab */
.profile-tab {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.profile-section {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

/* Big Five */
.bigfive-list {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.bigfive-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.bigfive-label {
  width: 4.5rem;
  flex-shrink: 0;
  font-size: 0.68rem;
  color: var(--text-secondary);
}

.bigfive-track {
  flex: 1;
  height: 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
}

.bigfive-fill {
  height: 100%;
  background: var(--accent, #3b82f6);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.bigfive-val {
  width: 2rem;
  text-align: right;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  color: var(--text-muted);
}

/* Values */
.values-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.3rem;
}

.values-item {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.35rem 0.5rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.05));
  border-radius: 4px;
}

.values-key {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.values-val {
  font-size: 0.7rem;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Life context */
.profile-text {
  font-size: 0.73rem;
  color: var(--text-secondary);
  line-height: 1.55;
  margin: 0;
}
.profile-text.muted { color: var(--text-muted); }

/* Loading dots (reuse common pattern) */
.loading-dots {
  display: flex;
  gap: 0.3rem;
}
.loading-dots span {
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 50%;
  background: var(--accent, #3b82f6);
  animation: dot-bounce 1.2s ease-in-out infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
