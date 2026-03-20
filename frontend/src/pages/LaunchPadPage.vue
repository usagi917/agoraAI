<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  getTemplates,
  listSimulations,
  createProject,
  uploadDocument,
  createSimulation,
  type TemplateResponse,
  type SimulationListItem,
} from '../api/client'
import InputPanel from '../components/InputPanel.vue'

const router = useRouter()

const templates = ref<TemplateResponse[]>([])
const selectedTemplate = ref('')
const selectedProfile = ref('standard')
const promptText = ref('')
const files = ref<File[]>([])
const isLoading = ref(false)
const recentSimulations = ref<SimulationListItem[]>([])

const profiles = [
  { value: 'preview', label: 'Preview', desc: '高速確認', detail: '因果推論2R → 多視点3C → PM評価' },
  { value: 'standard', label: 'Standard', desc: '標準分析', detail: '因果推論4R → 多視点5C → PM評価' },
  { value: 'quality', label: 'Quality', desc: '詳細分析', detail: '因果推論6R → 多視点8C → PM評価' },
]

onMounted(async () => {
  const [tmpl, sims] = await Promise.all([getTemplates(), listSimulations()])
  templates.value = tmpl
  recentSimulations.value = sims
  if (templates.value.length > 0) {
    selectedTemplate.value = templates.value[0].name
  }
})

async function handleLaunch() {
  if (!promptText.value.trim() && files.value.length === 0) return
  if (!selectedTemplate.value && files.value.length > 0) return

  isLoading.value = true
  try {
    let projectId: string | undefined

    if (files.value.length > 0) {
      const project = await createProject('新規分析')
      projectId = project.id
      for (const file of files.value) {
        await uploadDocument(project.id, file)
      }
    }

    const sim = await createSimulation({
      projectId,
      templateName: selectedTemplate.value,
      executionProfile: selectedProfile.value,
      promptText: promptText.value,
    })

    router.push(`/sim/${sim.id}`)
  } catch (error) {
    console.error('Launch error:', error)
    alert('シミュレーションの開始に失敗しました。')
  } finally {
    isLoading.value = false
  }
}

function getStatusColor(status: string) {
  switch (status) {
    case 'completed': return 'status-completed'
    case 'running': return 'status-running'
    case 'failed': return 'status-failed'
    default: return 'status-queued'
  }
}

function getPipelineStageLabel(stage: string) {
  switch (stage) {
    case 'single': return 'Stage 1'
    case 'swarm': return 'Stage 2'
    case 'pm_board': return 'Stage 3'
    case 'completed': return '完了'
    default: return stage
  }
}

</script>

<template>
  <div class="launchpad-page">
    <!-- Hero -->
    <section class="hero">
      <h2 class="hero-title">群生知能<br />シミュレーション</h2>
      <p class="hero-desc">プロンプトまたはドキュメントから世界モデルを構築し、因果推論・多視点検証・PM評価の3段階パイプラインで分析を実行します</p>
    </section>

    <!-- Sample Results -->
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">サンプルを見る</h3>
        <span class="section-badge">API Key不要</span>
      </div>
      <p class="sample-desc">APIキーなしでも分析結果のデモをご覧いただけます。</p>
      <div class="sample-grid">
        <router-link to="/sample/sample-business-001" class="sample-card">
          <div class="sample-card-top">
            <span class="sample-mode-tag">PIPELINE</span>
            <span class="sample-category">ビジネス分析</span>
          </div>
          <h4 class="sample-card-title">EVバッテリー市場参入分析</h4>
          <p class="sample-card-desc">市場規模・競合環境・技術トレンド・参入戦略を網羅した分析レポートと3Dナレッジグラフ</p>
          <span class="sample-card-cta">結果を見る &rarr;</span>
        </router-link>
        <router-link to="/sample/sample-pmboard-001" class="sample-card">
          <div class="sample-card-top">
            <span class="sample-mode-tag">PIPELINE</span>
            <span class="sample-category">事業検討</span>
          </div>
          <h4 class="sample-card-title">建設プロジェクト管理SaaS</h4>
          <p class="sample-card-desc">前提条件・リスク・勝利仮説・GTM戦略・30/60/90日計画を含むPM Board分析</p>
          <span class="sample-card-cta">結果を見る &rarr;</span>
        </router-link>
      </div>
    </section>

    <!-- Input Panel -->
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">入力</h3>
      </div>
      <InputPanel
        v-model="promptText"
        :files="files"
        @update:files="files = $event"
      />
    </section>

    <!-- Template Selection -->
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">テンプレート</h3>
        <span class="section-badge">{{ templates.length }} 件</span>
      </div>
      <div class="template-grid">
        <div
          v-for="tmpl in templates"
          :key="tmpl.name"
          class="template-card"
          :class="{ selected: selectedTemplate === tmpl.name }"
          @click="selectedTemplate = tmpl.name"
        >
          <div class="template-card-top">
            <div class="template-indicator" :class="{ active: selectedTemplate === tmpl.name }"></div>
            <span class="template-category">{{ tmpl.category }}</span>
          </div>
          <h4 class="template-name">{{ tmpl.display_name }}</h4>
          <p class="template-desc">{{ tmpl.description }}</p>
        </div>
      </div>
    </section>

    <!-- Profile Selection -->
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">実行プロファイル</h3>
      </div>
      <div class="profile-grid">
        <div
          v-for="p in profiles"
          :key="p.value"
          class="profile-card"
          :class="{ selected: selectedProfile === p.value }"
          @click="selectedProfile = p.value"
        >
          <h4 class="profile-name">{{ p.label }}</h4>
          <p class="profile-desc">{{ p.desc }}</p>
          <span class="profile-detail">{{ p.detail }}</span>
        </div>
      </div>
    </section>

    <!-- Launch Button -->
    <section class="section launch-section">
      <button
        class="btn btn-primary launch-button"
        :class="{ loading: isLoading }"
        :disabled="(!promptText.trim() && files.length === 0) || isLoading"
        @click="handleLaunch"
      >
        <span v-if="isLoading" class="spinner"></span>
        {{ isLoading ? '起動中...' : 'シミュレーション実行' }}
      </button>
    </section>

    <!-- History -->
    <section v-if="recentSimulations.length > 0" class="section">
      <div class="section-header">
        <h3 class="section-title">実行履歴</h3>
        <span class="section-badge">{{ recentSimulations.length }} 件</span>
      </div>
      <div class="history-list">
        <router-link
          v-for="sim in recentSimulations"
          :key="sim.id"
          :to="sim.status === 'completed' ? `/sim/${sim.id}/results` : `/sim/${sim.id}`"
          class="history-item"
        >
          <div class="history-left">
            <span class="status-dot" :class="getStatusColor(sim.status)"></span>
            <div class="history-info">
              <span class="history-template">
                {{ sim.template_name || 'プロンプト実行' }}
              </span>
              <span class="history-meta">
                {{ sim.execution_profile }}
                <template v-if="sim.pipeline_stage && sim.pipeline_stage !== 'pending' && sim.status === 'running'">
                  · {{ getPipelineStageLabel(sim.pipeline_stage) }}
                </template>
              </span>
            </div>
          </div>
          <div class="history-right">
            <span class="status-badge" :class="getStatusColor(sim.status)">{{ sim.status }}</span>
            <span class="history-date">{{ new Date(sim.created_at).toLocaleString('ja-JP') }}</span>
          </div>
        </router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.launchpad-page {
  display: flex;
  flex-direction: column;
  gap: clamp(1.25rem, 1vw + 1rem, 2rem);
}

.hero {
  text-align: center;
  padding: clamp(1.5rem, 4vw, 3rem) 0 0.5rem;
}

.hero-title {
  font-size: clamp(2rem, 4vw, 2.75rem);
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 1.08;
}

.hero-desc {
  margin: 0.75rem auto 0;
  font-size: clamp(0.88rem, 0.4vw + 0.8rem, 0.98rem);
  color: var(--text-secondary);
  max-width: 42rem;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.section-title { font-size: 0.9rem; font-weight: 600; letter-spacing: -0.01em; }
.section-badge { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); background: rgba(255,255,255,0.04); padding: 0.15rem 0.5rem; border-radius: 999px; border: 1px solid var(--border); }

.sample-desc {
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.sample-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  gap: 0.75rem;
}

.sample-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  cursor: pointer;
  transition: border-color 0.25s, box-shadow 0.25s;
  text-decoration: none;
  color: var(--text-primary);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sample-card:hover {
  border-color: var(--accent);
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.15);
}

.sample-card-top {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sample-mode-tag {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  font-weight: 700;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  background: var(--accent-subtle);
  color: var(--accent);
  text-transform: uppercase;
}

.sample-category {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--text-muted);
}

.sample-card-title {
  font-size: 0.95rem;
  font-weight: 600;
}

.sample-card-desc {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.sample-card-cta {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--accent);
  font-weight: 500;
  margin-top: auto;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 0.75rem;
}

.template-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  cursor: pointer;
  transition: border-color 0.25s;
  min-height: 100%;
}

.template-card:hover { border-color: rgba(255,255,255,0.12); }
.template-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.template-card-top { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.template-indicator { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); transition: all 0.3s; }
.template-indicator.active { background: var(--accent); box-shadow: 0 0 8px var(--accent-glow); }
.template-category { font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase; }
.template-name { font-size: 0.95rem; font-weight: 600; margin-bottom: 0.4rem; }
.template-desc { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.5; }

.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}

.profile-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  cursor: pointer;
  text-align: center;
  transition: border-color 0.25s;
}

.profile-card:hover { border-color: rgba(255,255,255,0.12); }
.profile-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.profile-name { font-family: var(--font-mono); font-size: 0.85rem; font-weight: 600; margin-bottom: 0.25rem; }
.profile-desc { font-size: 0.8rem; color: var(--text-secondary); }
.profile-detail { display: inline-block; margin-top: 0.5rem; font-family: var(--font-mono); font-size: 0.68rem; color: var(--text-muted); background: rgba(255,255,255,0.04); padding: 0.15rem 0.5rem; border-radius: 999px; }

.launch-section { text-align: center; padding: 1rem 0; }
.launch-button {
  width: min(100%, 28rem);
  font-size: 1rem;
  padding: 0.85rem 1.5rem;
  border-radius: var(--radius);
  gap: 0.6rem;
}

.spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.2); border-top-color: white; border-radius: 50%; animation: spin 0.6s linear infinite; }

.history-list { display: flex; flex-direction: column; gap: 0.35rem; }
.history-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.95rem var(--panel-padding);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  text-decoration: none;
  color: var(--text-primary);
  transition: all 0.2s;
}

.history-item:hover { border-color: rgba(255,255,255,0.1); background: var(--bg-elevated); }
.history-left {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  min-width: 0;
  flex: 1 1 auto;
}

.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-dot.status-completed { background: var(--success); box-shadow: 0 0 8px var(--success-glow); }
.status-dot.status-running { background: var(--accent); box-shadow: 0 0 8px var(--accent-glow); animation: pulse-dot 2s infinite; }
.status-dot.status-failed { background: var(--danger); }
.status-dot.status-queued { background: var(--text-muted); }
.history-info { display: flex; flex-direction: column; min-width: 0; gap: 0.2rem; }

.history-template {
  font-size: 0.85rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  min-width: 0;
}

.history-meta { font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted); word-break: break-word; }

.history-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.85rem;
  flex: 0 0 auto;
  flex-wrap: wrap;
}

.status-badge { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 4px; text-transform: uppercase; }
.status-badge.status-completed { background: rgba(34,197,94,0.15); color: var(--success); }
.status-badge.status-running { background: var(--accent-subtle); color: var(--accent); }
.status-badge.status-failed { background: rgba(239,68,68,0.15); color: var(--danger); }
.status-badge.status-queued { background: rgba(255,255,255,0.05); color: var(--text-muted); }
.history-date {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-muted);
  text-align: right;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .hero {
    padding-top: 1.5rem;
  }

  .history-item {
    flex-direction: column;
  }

  .history-right {
    width: 100%;
    justify-content: space-between;
  }
}

@media (max-width: 640px) {
  .launchpad-page {
    gap: 1rem;
  }

  .hero {
    text-align: left;
  }

  .hero-desc {
    margin-left: 0;
    margin-right: 0;
  }

  .template-grid,
  .profile-grid {
    grid-template-columns: 1fr;
  }

  .launch-section {
    padding-top: 0.5rem;
  }

  .launch-button {
    width: 100%;
  }

  .history-right {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.4rem;
  }

  .history-date {
    text-align: left;
    white-space: normal;
  }
}
</style>
