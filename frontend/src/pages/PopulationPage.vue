<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  listPopulations,
  getPopulationDetail,
  generatePopulation,
  forkPopulation,
  type PopulationResponse,
} from '../api/client'

const populations = ref<PopulationResponse[]>([])
const selectedPop = ref<any>(null)
const parentPop = ref<any>(null)
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
    parentPop.value = null
    selectedPop.value = await getPopulationDetail(popId)
    if (selectedPop.value?.parent_id) {
      parentPop.value = await getPopulationDetail(selectedPop.value.parent_id)
    }
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

// --- Demographics distribution helpers ---

interface DistItem {
  label: string
  count: number
  percent: number
}

function computeDistribution(agents: any[], key: string): DistItem[] {
  const counts: Record<string, number> = {}
  for (const a of agents) {
    const val = a.demographics?.[key]
    if (val != null) counts[String(val)] = (counts[String(val)] || 0) + 1
  }
  const total = agents.length || 1
  return Object.entries(counts)
    .map(([label, count]) => ({ label, count, percent: Math.round((count / total) * 100) }))
    .sort((a, b) => b.count - a.count)
}

function computeAgeDistribution(agents: any[]): DistItem[] {
  const buckets: Record<string, number> = {}
  for (const a of agents) {
    const age = a.demographics?.age
    if (age == null) continue
    const decade = `${Math.floor(age / 10) * 10}代`
    buckets[decade] = (buckets[decade] || 0) + 1
  }
  const total = agents.length || 1
  return Object.entries(buckets)
    .map(([label, count]) => ({ label, count, percent: Math.round((count / total) * 100) }))
    .sort((a, b) => {
      const numA = parseInt(a.label)
      const numB = parseInt(b.label)
      return numA - numB
    })
}

const occupationDist = computed(() =>
  selectedPop.value?.sample_agents ? computeDistribution(selectedPop.value.sample_agents, 'occupation') : [],
)

const regionDist = computed(() =>
  selectedPop.value?.sample_agents ? computeDistribution(selectedPop.value.sample_agents, 'region') : [],
)

const ageDist = computed(() =>
  selectedPop.value?.sample_agents ? computeAgeDistribution(selectedPop.value.sample_agents) : [],
)

// --- Fork diff ---

const parentOccupationDist = computed(() =>
  parentPop.value?.sample_agents ? computeDistribution(parentPop.value.sample_agents, 'occupation') : [],
)

const parentRegionDist = computed(() =>
  parentPop.value?.sample_agents ? computeDistribution(parentPop.value.sample_agents, 'region') : [],
)

const parentAgeDist = computed(() =>
  parentPop.value?.sample_agents ? computeAgeDistribution(parentPop.value.sample_agents) : [],
)

const hasForkDiff = computed(() => !!selectedPop.value?.parent_id && !!parentPop.value)
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
        <button
          class="btn btn-primary"
          data-testid="generate-button"
          :disabled="generating"
          @click="handleGenerate"
        >
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

      <!-- Version lineage -->
      <div v-if="hasForkDiff" data-testid="version-lineage" class="version-lineage">
        <span class="lineage-node">v{{ parentPop.version }}</span>
        <span class="lineage-arrow">&rarr;</span>
        <span class="lineage-node current">v{{ selectedPop.version }}</span>
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

      <!-- Demographics distribution charts -->
      <div v-if="selectedPop.sample_agents?.length" data-testid="demographics-charts" class="demographics-charts">
        <h4 class="subsection-title">デモグラフィック分布 (サンプル{{ selectedPop.sample_agents.length }}人)</h4>

        <div class="charts-grid">
          <!-- Occupation -->
          <div data-testid="chart-occupation" class="dist-chart">
            <h5 class="chart-title">職業</h5>
            <div class="dist-bars">
              <div v-for="item in occupationDist" :key="item.label" class="dist-row">
                <span class="dist-label">{{ item.label }}</span>
                <div class="dist-bar-track">
                  <div data-testid="dist-bar" class="dist-bar-fill" :style="{ width: item.percent + '%' }"></div>
                </div>
                <span class="dist-count">{{ item.count }}</span>
              </div>
            </div>
          </div>

          <!-- Region -->
          <div data-testid="chart-region" class="dist-chart">
            <h5 class="chart-title">地域</h5>
            <div class="dist-bars">
              <div v-for="item in regionDist" :key="item.label" class="dist-row">
                <span class="dist-label">{{ item.label }}</span>
                <div class="dist-bar-track">
                  <div data-testid="dist-bar" class="dist-bar-fill region" :style="{ width: item.percent + '%' }"></div>
                </div>
                <span class="dist-count">{{ item.count }}</span>
              </div>
            </div>
          </div>

          <!-- Age -->
          <div data-testid="chart-age" class="dist-chart">
            <h5 class="chart-title">年代</h5>
            <div class="dist-bars">
              <div v-for="item in ageDist" :key="item.label" class="dist-row">
                <span class="dist-label">{{ item.label }}</span>
                <div class="dist-bar-track">
                  <div data-testid="dist-bar" class="dist-bar-fill age" :style="{ width: item.percent + '%' }"></div>
                </div>
                <span class="dist-count">{{ item.count }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Fork diff -->
      <div v-if="hasForkDiff" data-testid="fork-diff" class="fork-diff">
        <h4 class="subsection-title">Fork 差分 (v{{ parentPop.version }} &rarr; v{{ selectedPop.version }})</h4>

        <div class="diff-grid">
          <div class="diff-column">
            <span class="diff-column-label">v{{ parentPop.version }} (親)</span>
            <div class="dist-bars">
              <div v-for="item in parentOccupationDist" :key="item.label" class="dist-row">
                <span class="dist-label">{{ item.label }}</span>
                <div class="dist-bar-track">
                  <div class="dist-bar-fill parent" :style="{ width: item.percent + '%' }"></div>
                </div>
                <span class="dist-count">{{ item.count }}</span>
              </div>
            </div>
          </div>
          <div class="diff-column">
            <span class="diff-column-label">v{{ selectedPop.version }} (現在)</span>
            <div class="dist-bars">
              <div v-for="item in occupationDist" :key="item.label" class="dist-row">
                <span class="dist-label">{{ item.label }}</span>
                <div class="dist-bar-track">
                  <div class="dist-bar-fill" :style="{ width: item.percent + '%' }"></div>
                </div>
                <span class="dist-count">{{ item.count }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sample agents -->
      <div v-if="selectedPop.sample_agents?.length" class="sample-agents">
        <h4 class="subsection-title">サンプルエージェント (先頭{{ selectedPop.sample_agents.length }}人)</h4>
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
.population-page { display: flex; flex-direction: column; gap: var(--section-gap); }
.hero { text-align: center; padding: clamp(1.5rem, 4vw, 3rem) 0 var(--space-2); }
.hero-title { font-size: var(--text-3xl); font-weight: 700; letter-spacing: -0.04em; }
.hero-desc { margin: var(--space-2) auto 0; font-size: var(--text-sm); color: var(--text-secondary); }
.error-banner { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius); padding: var(--space-3); color: var(--danger); font-size: var(--text-sm); }
.loading-text { font-size: var(--text-sm); color: var(--text-muted); }
.section-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-4); flex-wrap: wrap; }
.section-title { font-size: var(--text-sm); font-weight: 600; }
.section-badge { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-muted); background: rgba(255,255,255,0.04); padding: 0.15rem var(--space-2); border-radius: 999px; border: 1px solid var(--border); }
.pop-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: var(--space-3); }
.pop-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); cursor: pointer; transition: border-color 0.25s; display: flex; flex-direction: column; gap: var(--space-1); }
.pop-card:hover { border-color: rgba(255,255,255,0.12); }
.pop-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.pop-card-top { display: flex; justify-content: space-between; align-items: center; }
.pop-version { font-family: var(--font-mono); font-size: var(--text-xs); font-weight: 700; color: var(--accent); }
.pop-status { font-family: var(--font-mono); font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 3px; }
.pop-status.ready { background: rgba(34,197,94,0.15); color: var(--success); }
.pop-status.generating { background: var(--accent-subtle); color: var(--accent); }
.pop-count { font-size: var(--text-xl); font-weight: 700; }
.pop-date { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-muted); }
.pop-actions { margin-top: var(--space-1); }

/* Version lineage */
.version-lineage { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-4); font-family: var(--font-mono); font-size: var(--text-sm); }
.lineage-node { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: var(--space-1) var(--space-3); }
.lineage-node.current { border-color: var(--accent); color: var(--accent); font-weight: 700; }
.lineage-arrow { color: var(--text-muted); }

/* Stats */
.pop-detail-stats { display: flex; gap: var(--space-6); flex-wrap: wrap; margin-bottom: var(--space-4); }
.stat-item { display: flex; flex-direction: column; gap: var(--space-1); }
.stat-label { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-muted); text-transform: uppercase; }
.stat-value { font-size: var(--text-base); font-weight: 600; }

/* Demographics charts */
.demographics-charts { margin-bottom: var(--space-6); }
.subsection-title { font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-3); }
.charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--space-4); }
.dist-chart { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }
.chart-title { font-size: var(--text-xs); font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: var(--space-3); }
.dist-bars { display: flex; flex-direction: column; gap: var(--space-2); }
.dist-row { display: grid; grid-template-columns: 5rem 1fr 1.5rem; gap: var(--space-2); align-items: center; }
.dist-label { font-size: var(--text-xs); color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dist-bar-track { height: 6px; background: rgba(255,255,255,0.04); border-radius: 3px; overflow: hidden; }
.dist-bar-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.4s ease-out; min-width: 2px; }
.dist-bar-fill.region { background: var(--success); }
.dist-bar-fill.age { background: var(--warning); }
.dist-bar-fill.parent { background: var(--text-muted); }
.dist-count { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-muted); text-align: right; }

/* Fork diff */
.fork-diff { margin-bottom: var(--space-6); }
.diff-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }
.diff-column { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }
.diff-column-label { display: block; font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--space-3); text-transform: uppercase; }

/* Sample agents */
.sample-agents { margin-top: var(--space-2); }
.agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-2); }
.agent-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: var(--space-3); }
.agent-header { display: flex; justify-content: space-between; margin-bottom: var(--space-1); }
.agent-index { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--text-muted); }
.agent-backend { font-family: var(--font-mono); font-size: 0.65rem; color: var(--accent); background: var(--accent-subtle); padding: 0.1rem 0.3rem; border-radius: 3px; }
.agent-demo { font-size: var(--text-xs); color: var(--text-secondary); }
.agent-memory { font-size: var(--text-xs); color: var(--text-muted); margin-top: var(--space-1); font-style: italic; }

@media (max-width: 640px) {
  .diff-grid { grid-template-columns: 1fr; }
  .charts-grid { grid-template-columns: 1fr; }
}
</style>
