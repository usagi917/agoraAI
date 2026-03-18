<script setup lang="ts">
import { computed } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'

const store = useCognitiveStore()

const agents = computed(() => store.agentList)
const selected = computed(() => store.selectedAgent)

function selectAgent(agentId: string) {
  store.selectAgent(agentId)
}
</script>

<template>
  <div class="agent-mind-view">
    <div class="agent-list">
      <h3>エージェント一覧</h3>
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
.agent-list {
  width: 250px;
  overflow-y: auto;
}
.agent-card {
  padding: 0.75rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
}
.agent-card:hover {
  border-color: #4a90d9;
}
.agent-card.selected {
  border-color: #4a90d9;
  background: #f0f7ff;
}
.agent-name {
  font-weight: 600;
}
.agent-action {
  font-size: 0.85rem;
  color: #666;
  margin-top: 0.25rem;
}
.agent-detail {
  flex: 1;
  overflow-y: auto;
}
.bdi-section {
  margin-bottom: 1.5rem;
}
.bdi-section h4 {
  margin-bottom: 0.5rem;
  color: #333;
}
.belief-item, .desire-item, .intention-item {
  position: relative;
  padding: 0.5rem;
  margin-bottom: 0.25rem;
  border-radius: 4px;
  background: #f8f8f8;
}
.confidence-bar, .commitment-bar {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: rgba(74, 144, 217, 0.1);
  border-radius: 4px;
}
.confidence-value {
  float: right;
  font-size: 0.8rem;
  color: #888;
}
.priority-badge {
  display: inline-block;
  background: #4a90d9;
  color: white;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.75rem;
  margin-right: 0.5rem;
}
.reasoning-chain, .action-taken {
  padding: 0.75rem;
  background: #f5f5f5;
  border-radius: 6px;
  white-space: pre-wrap;
  font-size: 0.9rem;
  line-height: 1.5;
}
</style>
