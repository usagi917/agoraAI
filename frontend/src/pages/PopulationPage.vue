<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  listPopulations,
  getPopulationDetail,
  generatePopulation,
  forkPopulation,
  type PopulationResponse,
} from '../api/client'

const populations = ref<PopulationResponse[]>([])
const selectedPop = ref<any>(null)
const loading = ref(false)
const generating = ref(false)
const error = ref('')

onMounted(async () => {
  await loadPopulations()
})

async function loadPopulations() {
  loading.value = true
  try {
    populations.value = await listPopulations()
  } catch (e) {
    error.value = '人口リストの取得に失敗しました'
  } finally {
    loading.value = false
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    await generatePopulation(1000)
    await loadPopulations()
  } catch (e) {
    error.value = '人口生成に失敗しました'
  } finally {
    generating.value = false
  }
}

async function handleSelectPop(popId: string) {
  try {
    selectedPop.value = await getPopulationDetail(popId)
  } catch (e) {
    error.value = '人口詳細の取得に失敗しました'
  }
}

async function handleFork(popId: string) {
  try {
    await forkPopulation(popId)
    await loadPopulations()
  } catch (e) {
    error.value = 'フォークに失敗しました'
  }
}
</script>

<template>
  <div class="population-page">
    <section class="hero">
      <h2 class="hero-title">人口管理</h2>
      <p class="hero-desc">デジタル住民の世代を管理します</p>
    </section>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <section class="section">
      <div class="section-header">
        <h3 class="section-title">人口一覧</h3>
        <button class="btn btn-primary" :disabled="generating" @click="handleGenerate">
          {{ generating ? '生成中...' : '新規生成 (1,000人)' }}
        </button>
      </div>

      <div v-if="loading" class="loading-text">読み込み中...</div>

      <div v-else class="pop-list">
        <div
          v-for="pop in populations"
          :key="pop.id"
          class="pop-card"
          :class="{ selected: selectedPop?.id === pop.id }"
          @click="handleSelectPop(pop.id)"
        >
          <div class="pop-card-top">
            <span class="pop-version">v{{ pop.version }}</span>
            <span class="pop-status" :class="pop.status">{{ pop.status }}</span>
          </div>
          <div class="pop-count">{{ pop.agent_count.toLocaleString() }}人</div>
          <div class="pop-date">{{ new Date(pop.created_at).toLocaleString('ja-JP') }}</div>
          <div class="pop-actions">
            <button class="btn btn-ghost btn-sm" @click.stop="handleFork(pop.id)">Fork</button>
          </div>
        </div>
      </div>
    </section>

    <section v-if="selectedPop" class="section">
      <div class="section-header">
        <h3 class="section-title">人口詳細</h3>
        <span class="section-badge">v{{ selectedPop.version }}</span>
        <span v-if="selectedPop.parent_id" class="section-badge">Fork元: {{ selectedPop.parent_id.slice(0, 8) }}</span>
      </div>

      <div class="pop-detail-stats">
        <div class="stat-item">
          <span class="stat-label">エージェント数</span>
          <span class="stat-value">{{ selectedPop.agent_count.toLocaleString() }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">ステータス</span>
          <span class="stat-value">{{ selectedPop.status }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">作成日</span>
          <span class="stat-value">{{ new Date(selectedPop.created_at).toLocaleString('ja-JP') }}</span>
        </div>
      </div>

      <div v-if="selectedPop.sample_agents?.length" class="sample-agents">
        <h4 class="subsection-title">サンプルエージェント (先頭20人)</h4>
        <div class="agent-grid">
          <div v-for="agent in selectedPop.sample_agents" :key="agent.id" class="agent-card">
            <div class="agent-header">
              <span class="agent-index">#{{ agent.agent_index }}</span>
              <span class="agent-backend">{{ agent.llm_backend }}</span>
            </div>
            <div class="agent-demo">
              {{ agent.demographics?.occupation }} / {{ agent.demographics?.age }}歳 / {{ agent.demographics?.region }}
            </div>
            <div v-if="agent.memory_summary" class="agent-memory">{{ agent.memory_summary }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.population-page { display: flex; flex-direction: column; gap: clamp(1.25rem, 1vw + 1rem, 2rem); }
.hero { text-align: center; padding: clamp(1.5rem, 4vw, 3rem) 0 0.5rem; }
.hero-title { font-size: clamp(1.5rem, 3vw, 2rem); font-weight: 700; letter-spacing: -0.04em; }
.hero-desc { margin: 0.5rem auto 0; font-size: 0.88rem; color: var(--text-secondary); }
.error-banner { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius); padding: 0.75rem; color: var(--danger); font-size: 0.82rem; }
.loading-text { font-size: 0.82rem; color: var(--text-muted); }
.section-header { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }
.section-title { font-size: 0.9rem; font-weight: 600; }
.section-badge { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); background: rgba(255,255,255,0.04); padding: 0.15rem 0.5rem; border-radius: 999px; border: 1px solid var(--border); }
.pop-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.75rem; }
.pop-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); cursor: pointer; transition: border-color 0.25s; display: flex; flex-direction: column; gap: 0.35rem; }
.pop-card:hover { border-color: rgba(255,255,255,0.12); }
.pop-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.pop-card-top { display: flex; justify-content: space-between; align-items: center; }
.pop-version { font-family: var(--font-mono); font-size: 0.72rem; font-weight: 700; color: var(--accent); }
.pop-status { font-family: var(--font-mono); font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 3px; }
.pop-status.ready { background: rgba(34,197,94,0.15); color: var(--success); }
.pop-status.generating { background: var(--accent-subtle); color: var(--accent); }
.pop-count { font-size: 1.2rem; font-weight: 700; }
.pop-date { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); }
.pop-actions { margin-top: 0.25rem; }
.btn-sm { font-size: 0.72rem; padding: 0.25rem 0.5rem; }
.pop-detail-stats { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
.stat-item { display: flex; flex-direction: column; gap: 0.15rem; }
.stat-label { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; }
.stat-value { font-size: 1rem; font-weight: 600; }
.subsection-title { font-size: 0.82rem; font-weight: 600; margin-bottom: 0.5rem; }
.agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.5rem; }
.agent-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.6rem; }
.agent-header { display: flex; justify-content: space-between; margin-bottom: 0.25rem; }
.agent-index { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); }
.agent-backend { font-family: var(--font-mono); font-size: 0.65rem; color: var(--accent); background: var(--accent-subtle); padding: 0.1rem 0.3rem; border-radius: 3px; }
.agent-demo { font-size: 0.78rem; color: var(--text-secondary); }
.agent-memory { font-size: 0.72rem; color: var(--text-muted); margin-top: 0.25rem; font-style: italic; }
</style>
