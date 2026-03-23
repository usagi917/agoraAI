<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  getHealth,
  getTemplates,
  listSimulations,
  createProject,
  uploadDocument,
  createSimulation,
  type HealthResponse,
  type TemplateResponse,
  type SimulationListItem,
} from '../api/client'
import InputPanel from '../components/InputPanel.vue'

const router = useRouter()

const templates = ref<TemplateResponse[]>([])
const selectedTemplate = ref('')
const selectedProfile = ref('standard')
const selectedMode = ref('unified')
const promptText = ref('')
const files = ref<File[]>([])
const isLoading = ref(false)
const recentSimulations = ref<SimulationListItem[]>([])
const runtimeHealth = ref<HealthResponse | null>(null)
const bootstrapError = ref('')
const showAdvancedOptions = ref(false)

// Question Wizard state
const questionTemplates = [
  {
    id: 'market_entry',
    icon: '📊',
    title: 'この市場に参入すべきか？',
    desc: '市場環境・競合・参入障壁を社会反応から分析',
    steps: [
      { key: 'industry', label: '業界・市場', placeholder: '例: EV バッテリー市場、日本のペットフード市場' },
      { key: 'strengths', label: '自社の強み・制約', placeholder: '例: 独自の固体電池技術を保有、量産体制は未整備' },
      { key: 'focus', label: '特に知りたいこと', placeholder: '例: 競合の反応、顧客受容性、規制リスク' },
    ],
  },
  {
    id: 'product_acceptance',
    icon: '📦',
    title: 'この製品は受け入れられるか？',
    desc: '消費者・ステークホルダーの受容性を予測',
    steps: [
      { key: 'product', label: '製品・サービスの概要', placeholder: '例: AIチャットボットによる健康相談サービス' },
      { key: 'target', label: 'ターゲット層', placeholder: '例: 30-50代の健康意識が高い都市部の会社員' },
      { key: 'concern', label: '懸念事項', placeholder: '例: プライバシー、正確性、既存サービスとの差別化' },
    ],
  },
  {
    id: 'policy_impact',
    icon: '📜',
    title: 'この政策を導入したらどうなるか？',
    desc: '政策影響・世論支持・ステークホルダー反応を予測',
    steps: [
      { key: 'policy', label: '政策の概要', placeholder: '例: 週休3日制の義務化' },
      { key: 'region', label: '対象地域・層', placeholder: '例: 日本全国、従業員50人以上の企業' },
      { key: 'interest', label: '知りたいこと', placeholder: '例: 世論支持率、経済影響、ステークホルダー反応' },
    ],
  },
  {
    id: 'scenario_compare',
    icon: '🔄',
    title: 'AとBどちらが良いか？',
    desc: '2つの選択肢を社会反応ベースで比較',
    steps: [
      { key: 'optionA', label: '選択肢A', placeholder: '例: 新工場を国内に建設' },
      { key: 'optionB', label: '選択肢B', placeholder: '例: 東南アジアの既存工場を拡張' },
      { key: 'criteria', label: '比較基準', placeholder: '例: コスト、リスク、ステークホルダー受容性' },
    ],
  },
]

const selectedQuestionTemplate = ref<string | null>(null)
const wizardStepValues = ref<Record<string, string>>({})

const activeTemplate = computed(() =>
  questionTemplates.find(t => t.id === selectedQuestionTemplate.value) ?? null,
)

const wizardComplete = computed(() => {
  if (!activeTemplate.value) return false
  return activeTemplate.value.steps.every(s => wizardStepValues.value[s.key]?.trim())
})

// 質問テンプレートIDとバックエンドテンプレート名のマッピング
const questionToBackendTemplate: Record<string, string> = {
  market_entry: 'market_entry',
  policy_impact: 'policy_impact',
  product_acceptance: 'scenario_exploration',
  scenario_compare: 'scenario_exploration',
}

function selectQuestionTemplate(templateId: string) {
  selectedQuestionTemplate.value = templateId
  wizardStepValues.value = {}

  // バックエンドテンプレートを自動選択
  const backendName = questionToBackendTemplate[templateId]
  if (backendName) {
    const match = templates.value.find(t => t.name === backendName)
    if (match) {
      selectedTemplate.value = match.name
    }
  }
}

function clearQuestionTemplate() {
  selectedQuestionTemplate.value = null
  wizardStepValues.value = {}
}

function buildPromptFromWizard(): string {
  if (!activeTemplate.value) return ''
  const tmpl = activeTemplate.value
  const parts: string[] = [`【${tmpl.title}】`]
  for (const step of tmpl.steps) {
    const val = wizardStepValues.value[step.key]?.trim()
    if (val) {
      parts.push(`${step.label}: ${val}`)
    }
  }
  return parts.join('\n')
}

const modes = [
  { value: 'unified', label: 'Unified', desc: '統合シミュレーション', detail: '社会の脈動 → 評議会 → Decision Brief', badge: 'Default' },
  { value: 'pipeline', label: 'Pipeline', desc: '3段階分析', detail: '因果推論 → 多視点 → PM評価' },
  { value: 'meta_simulation', label: 'Meta Simulation', desc: '反復統合シミュレーション', detail: 'world → society → issue swarms → PM → intervention replay', badge: 'Beta' },
  { value: 'society_first', label: 'Society First', desc: '社会反応起点', detail: '社会反応 → Issue Colony → 市場仮説' },
  { value: 'society', label: 'Society', desc: '社会シミュレーション', detail: '1,000人の住民 → 選抜 → 活性化 → 評価', badge: 'Experimental' },
  { value: 'single', label: 'Single', desc: '単一エージェント', detail: '因果推論のみ' },
  { value: 'swarm', label: 'Swarm', desc: '多視点分析', detail: '複数コロニー並列実行' },
]

const profiles = [
  { value: 'preview', label: 'Preview', desc: '高速確認', detail: '因果推論2R → 多視点3C → PM評価' },
  { value: 'standard', label: 'Standard', desc: '標準分析', detail: '因果推論4R → 多視点5C → PM評価' },
  { value: 'quality', label: 'Quality', desc: '詳細分析', detail: '因果推論6R → 多視点8C → PM評価' },
]

const canLaunchLive = computed(() => {
  if (bootstrapError.value) return false
  return runtimeHealth.value?.live_simulation_available ?? false
})
const launchDisabled = computed(() => {
  if (!canLaunchLive.value) return true
  const hasWizardInput = wizardComplete.value
  const hasManualInput = promptText.value.trim() || files.value.length > 0
  return (!hasWizardInput && !hasManualInput) || isLoading.value
})
const launchLabel = computed(() => {
  if (isLoading.value) return '起動中...'
  if (!canLaunchLive.value) return 'ライブ実行は利用不可'
  if (selectedMode.value === 'unified') return '統合シミュレーション実行'
  if (selectedMode.value === 'society_first') return 'Society First を実行'
  return 'シミュレーション実行'
})

onMounted(async () => {
  try {
    const [health, tmpl, sims] = await Promise.all([getHealth(), getTemplates(), listSimulations()])
    runtimeHealth.value = health
    templates.value = tmpl
    recentSimulations.value = sims
    if (templates.value.length > 0) {
      selectedTemplate.value = templates.value[0].name
    }
  } catch (error) {
    console.error('Bootstrap error:', error)
    bootstrapError.value = 'バックエンドへの接続に失敗しました。コンテナ起動直後は数秒待って再読み込みしてください。'
  }
})

async function handleLaunch() {
  if (!canLaunchLive.value) return

  // Build final prompt: wizard prompt takes priority, then manual input
  const wizardPrompt = buildPromptFromWizard()
  const finalPrompt = wizardPrompt || promptText.value.trim()

  if (!finalPrompt && files.value.length === 0) return
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

    // Use 'unified' mode by default; advanced settings allow override
    const launchMode = showAdvancedOptions.value ? selectedMode.value : 'unified'

    const sim = await createSimulation({
      projectId,
      templateName: selectedTemplate.value,
      executionProfile: selectedProfile.value,
      mode: launchMode,
      promptText: finalPrompt,
      evidenceMode: 'strict',
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
      <h2 class="hero-title">Unified<br />Simulation Lab</h2>
      <p class="hero-desc">1つの質問から社会の脈動を測定し、10人の評議会が議論し、意思決定に直結する Decision Brief を生成します。質問テンプレートを選ぶか、自由にプロンプトを入力してください。</p>
    </section>

    <section v-if="bootstrapError || (runtimeHealth && !runtimeHealth.live_simulation_available)" class="runtime-notice" :class="{ warning: runtimeHealth && !runtimeHealth.live_simulation_available, error: bootstrapError }">
      <h3 class="section-title">{{ bootstrapError ? '接続待機中' : 'ライブ実行は未設定です' }}</h3>
      <p class="runtime-copy">
        {{ bootstrapError || runtimeHealth?.live_simulation_message }}
      </p>
      <p v-if="runtimeHealth && !runtimeHealth.live_simulation_available" class="runtime-hint">
        `docker compose up --build` だけでサンプル結果は見られます。ライブ実行を有効にするには、`OPENAI_API_KEY` を `.env` またはシェル環境変数で渡してください。
      </p>
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

    <!-- Question Wizard -->
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">質問テンプレート</h3>
        <span class="section-badge">{{ questionTemplates.length }} 種類</span>
      </div>
      <div class="question-templates">
        <button
          v-for="qt in questionTemplates"
          :key="qt.id"
          class="question-card"
          :class="{ selected: selectedQuestionTemplate === qt.id }"
          :data-testid="`question-${qt.id}`"
          @click="selectQuestionTemplate(qt.id)"
        >
          <span class="question-icon">{{ qt.icon }}</span>
          <div class="question-card-body">
            <span class="question-title">{{ qt.title }}</span>
            <span class="question-desc">{{ qt.desc }}</span>
          </div>
        </button>
      </div>

      <!-- Wizard Step Form -->
      <div v-if="activeTemplate" class="wizard-form">
        <div class="wizard-form-header">
          <h4 class="wizard-form-title">{{ activeTemplate.title }}</h4>
          <button class="btn btn-ghost wizard-clear" @click="clearQuestionTemplate">テンプレートを解除</button>
        </div>
        <div class="wizard-steps">
          <div v-for="step in activeTemplate.steps" :key="step.key" class="wizard-step">
            <label class="wizard-label" :for="`wizard-${step.key}`">{{ step.label }}</label>
            <input
              :id="`wizard-${step.key}`"
              v-model="wizardStepValues[step.key]"
              class="wizard-input"
              type="text"
              :placeholder="step.placeholder"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- Input Panel -->
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">{{ activeTemplate ? '追加の指示（任意）' : '指示' }}</h3>
      </div>
      <InputPanel
        v-model="promptText"
        :files="files"
        @update:files="files = $event"
      />
      <p class="section-note">
        テンプレートを使わない場合は、ここに質問を直接入力してください。既定では統合モード + strict evidence で実行し、文書を添付すると検証可能性が上がります。
      </p>
    </section>

    <section class="section">
      <div class="section-header">
        <h3 class="section-title">既定の実行導線</h3>
        <button class="btn btn-ghost section-toggle" type="button" @click="showAdvancedOptions = !showAdvancedOptions">
          {{ showAdvancedOptions ? '詳細設定を閉じる' : '詳細設定を開く' }}
        </button>
      </div>
      <div class="default-flow-card">
        <div class="default-flow-top">
          <div>
            <div class="default-flow-eyebrow">Unified Flow</div>
            <h4 class="default-flow-title">統合シミュレーションを既定で起動</h4>
          </div>
          <span class="mode-badge primary">Default</span>
        </div>
        <p class="default-flow-copy">
          1,000人の社会反応を測定し、10人の名前付き評議会が3ラウンド議論。最終的に Decision Brief を生成します。モードを理解しなくてもこのまま実行開始できます。
        </p>
        <div class="default-flow-pills">
          <span class="profile-detail">社会の脈動 (~90秒)</span>
          <span class="profile-detail">評議会議論 (~60秒)</span>
          <span class="profile-detail">統合分析 + Decision Brief (~30秒)</span>
        </div>
      </div>
      <div v-if="showAdvancedOptions" class="advanced-panel">
        <div class="advanced-section">
          <div class="section-header">
            <h3 class="section-title">実行モード</h3>
            <span class="section-badge">上級者向け</span>
          </div>
          <div class="profile-grid">
            <div
              v-for="m in modes"
              :key="m.value"
              class="profile-card"
              :class="{ selected: selectedMode === m.value }"
              :data-testid="`mode-card-${m.value}`"
              @click="selectedMode = m.value"
            >
              <div class="mode-card-top">
                <h4 class="profile-name">{{ m.label }}</h4>
                <span v-if="m.badge" class="mode-badge">{{ m.badge }}</span>
              </div>
              <p class="profile-desc">{{ m.desc }}</p>
              <span class="profile-detail">{{ m.detail }}</span>
            </div>
          </div>
          <p v-if="selectedMode === 'society'" class="section-note section-note-warning">
            `society` は experimental 扱いです。迷う場合は `society_first` を使ってください。
          </p>
        </div>

        <div class="advanced-section">
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
        </div>

        <div class="advanced-section">
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
        </div>
      </div>
    </section>

    <!-- Launch Button -->
    <section class="section launch-section">
      <button
        data-testid="launch-button"
        class="btn btn-primary launch-button"
        :class="{ loading: isLoading }"
        :disabled="launchDisabled"
        @click="handleLaunch"
      >
        <span v-if="isLoading" class="spinner"></span>
        {{ launchLabel }}
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

.runtime-notice {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  background: var(--bg-card);
}

.runtime-notice.warning {
  border-color: rgba(245, 158, 11, 0.35);
  background: rgba(245, 158, 11, 0.08);
}

.runtime-notice.error {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.08);
}

.runtime-copy {
  font-size: 0.84rem;
  color: var(--text-secondary);
  line-height: 1.6;
}

.runtime-hint {
  margin-top: 0.6rem;
  font-size: 0.76rem;
  color: var(--text-muted);
  line-height: 1.6;
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
.section-note { margin-top: 0.75rem; font-size: 0.78rem; color: var(--text-muted); line-height: 1.6; }
.section-note-warning { color: #f59e0b; }
.section-toggle { margin-left: auto; font-size: 0.78rem; }

.default-flow-card {
  background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(16,185,129,0.08));
  border: 1px solid rgba(99,102,241,0.24);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.default-flow-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.default-flow-eyebrow {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.default-flow-title {
  margin-top: 0.2rem;
  font-size: 1rem;
  font-weight: 600;
}

.default-flow-copy {
  font-size: 0.84rem;
  color: var(--text-secondary);
  line-height: 1.65;
}

.default-flow-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.question-templates {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}

.question-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: var(--panel-padding);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.25s, box-shadow 0.25s;
  text-align: left;
}

.question-card:hover { border-color: rgba(255,255,255,0.12); }
.question-card.selected { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }

.question-icon { font-size: 1.4rem; flex-shrink: 0; margin-top: 0.1rem; }

.question-card-body { display: flex; flex-direction: column; gap: 0.25rem; min-width: 0; }

.question-title { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.question-desc { font-size: 0.76rem; color: var(--text-muted); line-height: 1.45; }

.wizard-form {
  margin-top: 1rem;
  padding: var(--panel-padding);
  background: linear-gradient(135deg, rgba(99,102,241,0.08), rgba(16,185,129,0.05));
  border: 1px solid rgba(99,102,241,0.18);
  border-radius: var(--radius);
}

.wizard-form-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.wizard-form-title { font-size: 0.92rem; font-weight: 600; }
.wizard-clear { font-size: 0.72rem; }

.wizard-steps { display: flex; flex-direction: column; gap: 0.85rem; }

.wizard-step { display: flex; flex-direction: column; gap: 0.3rem; }

.wizard-label { font-size: 0.78rem; font-weight: 500; color: var(--text-secondary); }

.wizard-input {
  padding: 0.6rem 0.8rem;
  background: rgba(0,0,0,0.25);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 0.85rem;
  transition: border-color 0.2s;
}

.wizard-input:focus {
  outline: none;
  border-color: var(--accent);
}

.wizard-input::placeholder { color: var(--text-muted); font-size: 0.8rem; }

.advanced-panel {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.advanced-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

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
.mode-card-top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.25rem; }
.mode-badge { font-family: var(--font-mono); font-size: 0.64rem; text-transform: uppercase; letter-spacing: 0.06em; color: #f59e0b; background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.24); border-radius: 999px; padding: 0.12rem 0.45rem; }
.mode-badge.primary { color: var(--success); background: rgba(34,197,94,0.12); border-color: rgba(34,197,94,0.24); }
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

  .default-flow-top {
    flex-direction: column;
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
