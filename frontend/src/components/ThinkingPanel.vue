<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useCognitiveStore } from '../stores/cognitiveStore'
import { useAgentVisualizationStore } from '../stores/agentVisualizationStore'

const cognitiveStore = useCognitiveStore()
const vizStore = useAgentVisualizationStore()

const activeSection = ref<'reasoning' | 'bdi' | 'memory'>('reasoning')

const latestThought = computed(() => vizStore.latestThought)
const selectedAgent = computed(() => cognitiveStore.selectedAgent)
const agentMemories = computed(() => cognitiveStore.selectedAgentMemories)
const agentReflections = computed(() => cognitiveStore.selectedAgentReflections)

const thinkingAgentName = computed(() => {
  if (vizStore.thinkingAgentId) {
    const agent = cognitiveStore.agentStates[vizStore.thinkingAgentId]
    return agent?.agentName || vizStore.thinkingAgentId
  }
  return null
})

const isThinking = computed(() => vizStore.thinkingAgentId !== null)

// タイプライター効果
const displayedText = ref('')
const targetText = ref('')
let _typewriterInterval: ReturnType<typeof setInterval> | null = null

watch(() => latestThought.value?.reasoningChain, (newText) => {
  if (!newText) return
  if (_typewriterInterval) clearInterval(_typewriterInterval)
  targetText.value = newText
  displayedText.value = ''
  let i = 0
  _typewriterInterval = setInterval(() => {
    if (i < targetText.value.length) {
      displayedText.value = targetText.value.slice(0, i + 1)
      i++
    } else {
      if (_typewriterInterval) clearInterval(_typewriterInterval)
      _typewriterInterval = null
    }
  }, 15)
})

// BDI データ
const sortedBeliefs = computed(() => {
  if (!selectedAgent.value) return []
  return [...selectedAgent.value.beliefs]
    .sort((a, b) => b.confidence - a.confidence)
    .slice(0, 10)
})

const sortedDesires = computed(() => {
  if (!selectedAgent.value) return []
  return [...selectedAgent.value.desires]
    .sort((a, b) => b.priority - a.priority)
    .slice(0, 8)
})

const sortedIntentions = computed(() => {
  if (!selectedAgent.value) return []
  return [...selectedAgent.value.intentions]
    .sort((a, b) => b.commitment_strength - a.commitment_strength)
    .slice(0, 5)
})

// メモリ + リフレクション統合タイムライン
const memoryTimeline = computed(() => {
  const items: Array<{
    type: 'memory' | 'reflection'
    content: string
    importance: number
    round: number
    memoryType?: string
  }> = []

  for (const m of agentMemories.value.slice(-20)) {
    items.push({
      type: 'memory',
      content: m.content,
      importance: m.importance,
      round: m.round,
      memoryType: m.memoryType,
    })
  }

  for (const r of agentReflections.value.slice(-10)) {
    items.push({
      type: 'reflection',
      content: r.insight,
      importance: r.importance,
      round: r.round,
    })
  }

  return items.sort((a, b) => a.round - b.round)
})

const recentThoughts = computed(() => vizStore.recentThoughts.slice(-8).reverse())

onBeforeUnmount(() => {
  if (_typewriterInterval) {
    clearInterval(_typewriterInterval)
    _typewriterInterval = null
  }
})
</script>

<template>
  <div class="thinking-panel">
    <!-- セクション切り替え -->
    <div class="section-switcher">
      <button
        v-for="sec in (['reasoning', 'bdi', 'memory'] as const)"
        :key="sec"
        :class="['section-btn', { active: activeSection === sec }]"
        @click="activeSection = sec"
      >
        {{ sec === 'reasoning' ? '推論' : sec === 'bdi' ? 'BDI' : '記憶' }}
      </button>
    </div>

    <!-- 思考中インジケーター -->
    <div v-if="isThinking" class="thinking-indicator">
      <span class="thinking-dot" />
      <span class="thinking-label">{{ thinkingAgentName }} 思考中...</span>
    </div>

    <!-- 推論セクション -->
    <div v-if="activeSection === 'reasoning'" class="section-content">
      <div v-if="displayedText" class="reasoning-stream">
        <div class="reasoning-header">
          <span class="reasoning-agent">{{ latestThought?.agentName }}</span>
          <span v-if="latestThought?.chosenAction" class="reasoning-action">→ {{ latestThought.chosenAction }}</span>
        </div>
        <pre class="reasoning-text">{{ displayedText }}<span v-if="displayedText.length < (targetText.length)" class="cursor">|</span></pre>
      </div>

      <!-- 直近の思考履歴 -->
      <div v-if="recentThoughts.length > 0" class="thought-history">
        <div class="history-label">直近の推論</div>
        <div
          v-for="(thought, idx) in recentThoughts"
          :key="idx"
          class="thought-card"
        >
          <div class="thought-header">
            <span class="thought-agent">{{ thought.agentName }}</span>
            <span class="thought-action">{{ thought.chosenAction }}</span>
          </div>
          <div class="thought-reasoning">{{ thought.reasoningChain.slice(0, 150) }}{{ thought.reasoningChain.length > 150 ? '...' : '' }}</div>
        </div>
      </div>

      <div v-if="!displayedText && recentThoughts.length === 0" class="empty-state">
        エージェントの推論データを待機中...
      </div>
    </div>

    <!-- BDI セクション -->
    <div v-if="activeSection === 'bdi'" class="section-content">
      <div v-if="selectedAgent" class="bdi-grid">
        <!-- 信念 -->
        <div class="bdi-card beliefs-card">
          <div class="bdi-title">信念 (Beliefs)</div>
          <div v-for="(b, idx) in sortedBeliefs" :key="idx" class="bdi-item">
            <div class="bdi-item-label">{{ b.proposition }}</div>
            <div class="bdi-bar-track">
              <div
                class="bdi-bar-fill beliefs-fill"
                :style="{ width: `${b.confidence * 100}%` }"
              />
            </div>
            <span class="bdi-value">{{ (b.confidence * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="sortedBeliefs.length === 0" class="bdi-empty">データなし</div>
        </div>

        <!-- 欲求 -->
        <div class="bdi-card desires-card">
          <div class="bdi-title">欲求 (Desires)</div>
          <div v-for="(d, idx) in sortedDesires" :key="idx" class="bdi-item">
            <div class="bdi-item-label">{{ d.goal_text }}</div>
            <div class="bdi-bar-track">
              <div
                class="bdi-bar-fill desires-fill"
                :style="{ width: `${d.priority * 100}%` }"
              />
            </div>
            <span class="bdi-value">{{ (d.priority * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="sortedDesires.length === 0" class="bdi-empty">データなし</div>
        </div>

        <!-- 意図 -->
        <div class="bdi-card intentions-card">
          <div class="bdi-title">意図 (Intentions)</div>
          <div v-for="(i, idx) in sortedIntentions" :key="idx" class="bdi-item">
            <div class="bdi-item-label">{{ i.plan_text }}</div>
            <div class="bdi-bar-track">
              <div
                class="bdi-bar-fill intentions-fill"
                :style="{ width: `${i.commitment_strength * 100}%` }"
              />
            </div>
            <span class="bdi-value">{{ (i.commitment_strength * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="sortedIntentions.length === 0" class="bdi-empty">データなし</div>
        </div>
      </div>

      <div v-else class="empty-state">
        グラフ上のエージェントをクリックして BDI 状態を表示
      </div>
    </div>

    <!-- 記憶セクション -->
    <div v-if="activeSection === 'memory'" class="section-content">
      <div v-if="memoryTimeline.length > 0" class="memory-timeline">
        <div
          v-for="(item, idx) in memoryTimeline"
          :key="idx"
          :class="['memory-item', item.type]"
        >
          <div class="memory-dot" />
          <div class="memory-content">
            <div class="memory-meta">
              <span class="memory-round">R{{ item.round }}</span>
              <span v-if="item.type === 'memory' && item.memoryType" class="memory-type-badge">
                {{ item.memoryType }}
              </span>
              <span v-if="item.type === 'reflection'" class="memory-type-badge reflection-badge">
                reflection
              </span>
              <span class="memory-importance" :style="{ opacity: 0.4 + item.importance * 0.6 }">
                ★{{ item.importance.toFixed(1) }}
              </span>
            </div>
            <div class="memory-text">{{ item.content }}</div>
          </div>
        </div>
      </div>

      <div v-else class="empty-state">
        エージェントを選択して記憶タイムラインを表示
      </div>
    </div>
  </div>
</template>

<style scoped>
.thinking-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  height: 100%;
  overflow-y: auto;
}

.section-switcher {
  display: flex;
  gap: 0.25rem;
  padding: 0.25rem;
  background: var(--bg-elevated);
  border-radius: var(--radius-sm);
}

.section-btn {
  flex: 1;
  padding: 0.4rem 0.5rem;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.section-btn.active {
  background: var(--bg-card);
  color: var(--text-primary);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
}

/* 思考中インジケーター */
.thinking-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.2);
  border-radius: var(--radius-sm);
}

.thinking-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  animation: pulse-dot 2s ease-in-out infinite;
}

.thinking-label {
  font-size: 0.75rem;
  color: var(--accent);
  font-weight: 500;
}

/* 推論ストリーム */
.reasoning-stream {
  background: var(--bg-elevated);
  border-left: 3px solid var(--accent);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  padding: 0.75rem;
}

.reasoning-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.reasoning-agent {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent);
}

.reasoning-action {
  font-size: 0.7rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.reasoning-text {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.cursor {
  animation: blink 0.8s step-end infinite;
  color: var(--accent);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* 思考履歴 */
.thought-history {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.history-label {
  font-size: 0.68rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.thought-card {
  padding: 0.5rem 0.6rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.thought-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}

.thought-agent {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-primary);
}

.thought-action {
  font-size: 0.65rem;
  color: var(--accent);
  font-family: var(--font-mono);
}

.thought-reasoning {
  font-size: 0.68rem;
  color: var(--text-muted);
  line-height: 1.4;
}

/* BDI グリッド */
.bdi-grid {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.bdi-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.6rem;
}

.bdi-title {
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.bdi-item {
  display: grid;
  grid-template-columns: 1fr 60px 30px;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.35rem;
}

.bdi-item-label {
  font-size: 0.68rem;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bdi-bar-track {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}

.bdi-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s ease;
}

.beliefs-fill { background: var(--accent); }
.desires-fill { background: var(--warning); }
.intentions-fill { background: var(--success); }

.bdi-value {
  font-size: 0.6rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
  text-align: right;
}

.bdi-empty {
  font-size: 0.68rem;
  color: var(--text-muted);
  font-style: italic;
}

/* 記憶タイムライン */
.memory-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-left: 1rem;
  border-left: 1px solid var(--border);
}

.memory-item {
  display: flex;
  gap: 0.6rem;
  padding: 0.4rem 0;
  position: relative;
}

.memory-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 0.15rem;
  position: absolute;
  left: -1.35rem;
}

.memory-item.memory .memory-dot {
  background: var(--accent);
}

.memory-item.reflection .memory-dot {
  background: var(--warning);
}

.memory-item.reflection {
  padding-left: 0.5rem;
}

.memory-content {
  flex: 1;
}

.memory-meta {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.15rem;
}

.memory-round {
  font-size: 0.6rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.memory-type-badge {
  font-size: 0.58rem;
  padding: 0.08rem 0.3rem;
  border-radius: 3px;
  background: rgba(59, 130, 246, 0.15);
  color: var(--accent);
}

.reflection-badge {
  background: rgba(245, 158, 11, 0.15);
  color: var(--warning);
}

.memory-importance {
  font-size: 0.6rem;
  color: var(--warning);
}

.memory-text {
  font-size: 0.7rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* セクションコンテンツ */
.section-content {
  flex: 1;
  overflow-y: auto;
}

/* 空状態 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 6rem;
  color: var(--text-muted);
  font-size: 0.75rem;
  text-align: center;
}
</style>
