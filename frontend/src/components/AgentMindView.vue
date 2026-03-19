<script setup lang="ts">
import { computed } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

const store = useCognitiveStore()

const agents = computed(() => store.agentList)
const selected = computed(() => store.selectedAgent)

const currentRound = computed(() => selected.value?.round ?? 0)

/** Build a trust map from the selected agent's beliefs about other agents */
const trustMap = computed(() => {
  if (!selected.value) return []
  const tomRelations = store.tomRelations.filter(
    (r) => r.observer === selected.value!.agentName
  )
  return tomRelations.map((r) => ({
    target: r.target,
    trust: r.trustLevel,
  }))
})

function selectAgent(agentId: string) {
  store.selectAgent(agentId)
}
</script>

<template>
  <div class="agent-mind-view">
    <div class="agent-list">
      <div class="sidebar-header">
        <h3>エージェント一覧</h3>
        <span v-if="currentRound" class="round-badge">Round {{ currentRound }}</span>
      </div>
      <div
        v-for="agent in agents"
        :key="agent.agentId"
        class="agent-card"
        :class="{ selected: agent.agentId === store.selectedAgentId }"
        @click="selectAgent(agent.agentId)"
      >
        <div class="agent-name">{{ agent.agentName }}</div>
        <div class="agent-action">{{ agent.actionTaken?.slice(0, 80) }}...</div>
      </div>
    </div>

    <div v-if="selected" class="agent-detail">
      <h3>{{ selected.agentName }} - BDI状態</h3>

      <!-- 信念 -->
      <div class="bdi-section">
        <h4>信念 (Beliefs)</h4>
        <div v-for="belief in selected.beliefs.slice(0, 10)" :key="belief.proposition" class="belief-item">
          <span class="confidence-bar" :style="{ width: belief.confidence * 100 + '%' }"></span>
          <span class="belief-text">{{ belief.proposition }}</span>
          <span class="confidence-value">{{ (belief.confidence * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <!-- 欲求 -->
      <div class="bdi-section">
        <h4>欲求 (Desires)</h4>
        <div v-for="desire in selected.desires" :key="desire.goal_text" class="desire-item">
          <span class="priority-badge">P{{ (desire.priority * 10).toFixed(0) }}</span>
          {{ desire.goal_text }}
        </div>
      </div>

      <!-- 意図 -->
      <div class="bdi-section">
        <h4>意図 (Intentions)</h4>
        <div v-for="intention in selected.intentions" :key="intention.plan_text" class="intention-item">
          <span class="commitment-bar" :style="{ width: intention.commitment_strength * 100 + '%' }"></span>
          {{ intention.plan_text }}
        </div>
      </div>

      <!-- 信頼マップ -->
      <div v-if="trustMap.length > 0" class="bdi-section">
        <h4>信頼マップ (Trust Map)</h4>
        <div v-for="entry in trustMap" :key="entry.target" class="trust-map-item">
          <span class="trust-target-name">{{ entry.target }}</span>
          <span class="trust-bar-track">
            <span
              class="trust-bar-fill"
              :class="{
                'trust-high': entry.trust >= 0.7,
                'trust-mid': entry.trust >= 0.4 && entry.trust < 0.7,
                'trust-low': entry.trust < 0.4,
              }"
              :style="{ width: entry.trust * 100 + '%' }"
            ></span>
          </span>
          <span class="trust-value">{{ (entry.trust * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <!-- 推論チェーン -->
      <div class="bdi-section">
        <h4>推論チェーン</h4>
        <div class="reasoning-chain">{{ selected.reasoningChain }}</div>
      </div>

      <!-- 行動 -->
      <div class="bdi-section">
        <h4>実行した行動</h4>
        <div class="action-taken">{{ selected.actionTaken }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-mind-view {
  display: flex;
  gap: 1rem;
  height: 100%;
}

/* ---- Sidebar ---- */
.agent-list {
  width: 260px;
  overflow-y: auto;
  border-right: 1px solid var(--border);
  padding-right: 1rem;
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.sidebar-header h3 {
  margin: 0;
  color: var(--text-primary);
}
.round-badge {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-sm);
  background: var(--accent-subtle);
  color: var(--accent);
  border: 1px solid var(--border-active);
}

.agent-card {
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 0.5rem;
  cursor: pointer;
  background: var(--bg-card);
  transition: all 0.2s;
}
.agent-card:hover {
  border-color: var(--border-active);
  background: var(--bg-surface);
}
.agent-card.selected {
  border-color: var(--accent);
  background: var(--bg-surface);
  box-shadow: 0 0 12px var(--accent-glow);
}
.agent-name {
  font-weight: 600;
  color: var(--text-primary);
}
.agent-action {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
  line-height: 1.4;
}

/* ---- Detail ---- */
.agent-detail {
  flex: 1;
  overflow-y: auto;
}
.agent-detail h3 {
  color: var(--text-primary);
}
.bdi-section {
  margin-bottom: 1.5rem;
}
.bdi-section h4 {
  margin-bottom: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* Belief / Desire / Intention items */
.belief-item,
.desire-item,
.intention-item {
  position: relative;
  padding: 0.5rem 0.6rem;
  margin-bottom: 0.25rem;
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border);
}

/* Animated gradient bars */
.confidence-bar,
.commitment-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: linear-gradient(90deg, var(--accent-glow), transparent);
  border-radius: var(--radius-sm);
  transition: width 0.6s ease;
}
.confidence-value {
  float: right;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-muted);
}
.belief-text {
  position: relative;
  z-index: 1;
}

.priority-badge {
  display: inline-block;
  background: var(--accent);
  color: #fff;
  padding: 0.1rem 0.4rem;
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  margin-right: 0.5rem;
}

/* ---- Trust Map ---- */
.trust-map-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.35rem 0;
}
.trust-target-name {
  min-width: 90px;
  font-size: 0.85rem;
  color: var(--text-primary);
}
.trust-bar-track {
  flex: 1;
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.trust-bar-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}
.trust-bar-fill.trust-high {
  background: var(--success);
  box-shadow: 0 0 6px var(--success-glow);
}
.trust-bar-fill.trust-mid {
  background: var(--warning);
  box-shadow: 0 0 6px var(--warning-glow);
}
.trust-bar-fill.trust-low {
  background: var(--danger);
  box-shadow: 0 0 6px var(--danger-glow);
}
.trust-value {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--text-muted);
  min-width: 36px;
  text-align: right;
}

/* Reasoning / Action blocks */
.reasoning-chain,
.action-taken {
  padding: 0.75rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  white-space: pre-wrap;
  font-size: 0.9rem;
  line-height: 1.5;
  color: var(--text-primary);
  font-family: var(--font-mono);
}
</style>
