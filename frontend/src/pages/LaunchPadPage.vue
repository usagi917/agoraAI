<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  getHealth,
  getTemplates,
  listSimulations,
  listPopulations,
  createProject,
  uploadDocument,
  createSimulation,
  type HealthResponse,
  type TemplateResponse,
  type SimulationListItem,
} from '../api/client'
import { useScenarioPairStore } from '../stores/scenarioPairStore'
import InputPanel from '../components/InputPanel.vue'

const router = useRouter()
const scenarioPairStore = useScenarioPairStore()

const templates = ref<TemplateResponse[]>([])
const selectedTemplate = ref('')
const selectedProfile = ref('standard')
const selectedPreset = ref('standard')

const presets = [
  { id: 'quick', label: 'Quick', desc: '社会反応 → レポート', time: '約1分', phases: 2 },
  { id: 'standard', label: 'Standard', desc: '社会反応 → 評議会 → レポート', time: '約3分', phases: 3 },
  { id: 'deep', label: 'Deep', desc: '全フェーズ投入・最高品質', time: '約8分', phases: 5 },
  { id: 'research', label: 'Research', desc: 'イシュー深掘り＋介入テスト', time: '約10分', phases: 5 },
  { id: 'baseline', label: 'Baseline', desc: '単一LLM・学術比較用', time: '約30秒', phases: 1 },
]
const promptText = ref('')
const files = ref<File[]>([])
const isLoading = ref(false)
const recentSimulations = ref<SimulationListItem[]>([])
const runtimeHealth = ref<HealthResponse | null>(null)
const bootstrapError = ref('')
// advanced options removed for simplicity

// Scenario Comparison state
const scenarioDecisionContext = ref('')
const scenarioInterventionParams = ref(
  JSON.stringify(
    { policy_type: '住宅補助金', amount: '月3万円', target_population: '年収400万円以下', duration: '12ヶ月' },
    null,
    2,
  ),
)
const scenarioPreset = ref('standard')
const scenarioPopulationId = ref('')
const scenarioIsLoading = ref(false)
const scenarioError = ref('')
const availablePopulations = ref<Array<{ id: string; agent_count: number; status: string }>>([])

async function handleScenarioCompare() {
  scenarioError.value = ''
  if (!scenarioDecisionContext.value.trim()) {
    scenarioError.value = '政策の説明を入力してください'
    return
  }
  let parsedParams: Record<string, unknown>
  try {
    parsedParams = JSON.parse(scenarioInterventionParams.value)
  } catch {
    scenarioError.value = '介入パラメータのJSON形式が正しくありません'
    return
  }
  if (!scenarioPopulationId.value) {
    scenarioError.value = '母集団を選択してください'
    return
  }
  scenarioIsLoading.value = true
  try {
    const pair = await scenarioPairStore.createScenarioPair({
      population_id: scenarioPopulationId.value,
      decision_context: scenarioDecisionContext.value.trim(),
      intervention_params: parsedParams,
      preset: scenarioPreset.value,
    })
    router.push(`/scenario/${pair.id}`)
  } catch {
    scenarioError.value = scenarioPairStore.error || 'シナリオ比較の作成に失敗しました'
  } finally {
    scenarioIsLoading.value = false
  }
}

// Question Wizard state
const questionTemplates = [
  {
    id: 'market_entry',
    icon: '📊',
    title: 'この市場に参入すべきか？',
    desc: '市場環境・競合・参入障壁を社会反応から分析',
    accentColor: '#3b82f6',
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
    accentColor: '#22c55e',
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
    accentColor: '#a855f7',
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
    accentColor: '#f97316',
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

// Legacy mode list (backward compat — no longer exposed in UI)
const _legacyModes = ['unified', 'pipeline', 'meta_simulation', 'society_first', 'society', 'single', 'swarm'] as const
void _legacyModes

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
// launchLabel は inline で処理

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
  // Load populations for scenario comparison (non-blocking)
  try {
    const pops = await listPopulations()
    availablePopulations.value = pops
    if (pops.length > 0) {
      scenarioPopulationId.value = pops[0].id
    }
  } catch {
    // Populations may not be available yet — not critical
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

    const sim = await createSimulation({
      projectId,
      templateName: selectedTemplate.value,
      executionProfile: selectedProfile.value,
      mode: selectedPreset.value,
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

function getStatusLabel(status: string) {
  switch (status) {
    case 'completed': return '完了'
    case 'running': return '実行中'
    case 'failed': return '失敗'
    default: return '待機中'
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
      <h2 class="hero-title">ひとつの問いから、<br />社会の反応を予測する</h2>
      <p class="hero-desc">AIエージェント1,000人が議論し、代表評議会が検証し、あなたの意思決定を支える Decision Brief を生成します。</p>
    </section>

    <section v-if="bootstrapError || (runtimeHealth && !runtimeHealth.live_simulation_available)" class="runtime-notice" :class="{ warning: runtimeHealth && !runtimeHealth.live_simulation_available, error: bootstrapError }">
      <h3 class="section-title">{{ bootstrapError ? '接続待機中' : 'ライブ実行は未設定です' }}</h3>
      <p class="runtime-copy">
        {{ bootstrapError || runtimeHealth?.live_simulation_message }}
      </p>
      <p v-if="runtimeHealth && !runtimeHealth.live_simulation_available" class="runtime-hint">
        ライブ実行を有効にするには、`OPENAI_API_KEY` を `.env` またはシェル環境変数で渡してください。
      </p>
    </section>

    <!-- Unified Input Section -->
    <section class="section input-section">
      <h3 class="input-section-title">何を分析しますか？</h3>
      <p class="input-section-hint">テンプレートを選ぶか、自由に入力してください</p>

      <!-- Question Template Cards -->
      <div class="question-templates">
        <button
          v-for="qt in questionTemplates"
          :key="qt.id"
          class="question-card"
          :class="{ selected: selectedQuestionTemplate === qt.id }"
          :style="{ '--card-accent': qt.accentColor }"
          :data-testid="`question-${qt.id}`"
          @click="selectQuestionTemplate(qt.id)"
        >
          <span class="question-card-bar" />
          <span class="question-icon">{{ qt.icon }}</span>
          <span class="question-title">{{ qt.title }}</span>
        </button>
      </div>

      <!-- Wizard Fields (inline, appears when template selected) -->
      <div v-if="activeTemplate" class="wizard-inline">
        <div class="wizard-inline-header">
          <span class="wizard-inline-title">{{ activeTemplate.title }}</span>
          <button class="wizard-clear-btn" @click="clearQuestionTemplate">&times;</button>
        </div>
        <div class="wizard-fields">
          <div v-for="step in activeTemplate.steps" :key="step.key" class="wizard-field">
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

      <!-- Free Prompt (visible when no template, or as additional input) -->
      <div v-if="!activeTemplate" class="free-prompt">
        <label class="free-prompt-label" for="launchpad-prompt">分析プロンプト</label>
        <textarea
          id="launchpad-prompt"
          name="launchpad-prompt"
          v-model="promptText"
          class="prompt-textarea"
          data-testid="launchpad-prompt"
          placeholder="もし〜なら？ — 分析したい仮説やシナリオを入力してください"
          rows="3"
        />
      </div>

      <!-- File Upload (compact) -->
      <details class="file-drop-details">
        <summary class="file-drop-summary">ファイルを添付（任意）</summary>
        <InputPanel
          :files="files"
          @update:files="files = $event"
        />
      </details>

      <!-- Preset Selection -->
      <div class="preset-section">
        <h4 class="preset-title">分析モード</h4>
        <div class="preset-cards">
          <button
            v-for="p in presets"
            :key="p.id"
            class="preset-card"
            :class="{ selected: selectedPreset === p.id, recommended: p.id === 'standard' }"
            :data-testid="`preset-${p.id}`"
            @click="selectedPreset = p.id"
          >
            <span v-if="p.id === 'standard'" class="preset-recommended">おすすめ</span>
            <span class="preset-label">{{ p.label }}</span>
            <span class="preset-desc">{{ p.desc }}</span>
            <span class="preset-meta">{{ p.time }} · {{ p.phases }} phase{{ p.phases > 1 ? 's' : '' }}</span>
          </button>
        </div>
      </div>

      <!-- Launch Button (inline) -->
      <button
        data-testid="launch-button"
        class="btn btn-primary launch-button"
        :class="{ loading: isLoading }"
        :disabled="launchDisabled"
        @click="handleLaunch"
      >
        <span v-if="isLoading" class="spinner"></span>
        {{ isLoading ? '起動中...' : '分析を開始' }}
      </button>
      <p class="launch-note">
        {{ presets.find(p => p.id === selectedPreset)?.time ?? '約3分' }}
        — {{ presets.find(p => p.id === selectedPreset)?.desc ?? '' }}
      </p>
    </section>

    <!-- How It Works (collapsed) -->
    <details class="how-it-works">
      <summary class="how-it-works-summary">仕組みを見る</summary>
      <div class="phase-workflow">
        <div class="phase-step"><span class="phase-num">01</span><strong>Society Pulse</strong> — 1,000人のAIエージェントから意見を収集</div>
        <div class="phase-step"><span class="phase-num">02</span><strong>Council</strong> — 10人の代表者が3ラウンドの議論</div>
        <div class="phase-step"><span class="phase-num">03</span><strong>Synthesis</strong> — エビデンス付きのDecision Briefを生成</div>
      </div>
    </details>

    <!-- Scenario Comparison -->
    <section class="section scenario-section" data-testid="scenario-comparison-section">
      <div class="scenario-header">
        <span class="scenario-accent-bar" />
        <div>
          <h3 class="scenario-title">シナリオ比較</h3>
          <p class="scenario-desc">ベースラインと政策介入を比較し、影響を可視化します</p>
        </div>
      </div>

      <div class="scenario-form">
        <div class="scenario-field">
          <label class="wizard-label" for="scenario-decision-context">政策の説明</label>
          <input
            id="scenario-decision-context"
            v-model="scenarioDecisionContext"
            class="wizard-input"
            type="text"
            placeholder="例: 住宅補助金制度の導入"
            data-testid="scenario-decision-context"
          />
        </div>

        <div class="scenario-field">
          <label class="wizard-label" for="scenario-intervention-params">介入パラメータ (JSON)</label>
          <textarea
            id="scenario-intervention-params"
            v-model="scenarioInterventionParams"
            class="prompt-textarea scenario-textarea"
            rows="5"
            data-testid="scenario-intervention-params"
          />
        </div>

        <div class="scenario-field" v-if="availablePopulations.length > 0">
          <label class="wizard-label" for="scenario-population">母集団</label>
          <select
            id="scenario-population"
            v-model="scenarioPopulationId"
            class="wizard-input scenario-select"
            data-testid="scenario-population"
          >
            <option v-for="pop in availablePopulations" :key="pop.id" :value="pop.id">
              {{ pop.id.slice(0, 8) }}... ({{ pop.agent_count }}人)
            </option>
          </select>
        </div>
        <p v-else class="scenario-no-pop">母集団がありません。<router-link to="/populations">母集団を作成</router-link>してください。</p>

        <div class="scenario-field">
          <label class="wizard-label">分析モード</label>
          <div class="preset-cards">
            <button
              v-for="p in presets"
              :key="p.id"
              class="preset-card"
              :class="{ selected: scenarioPreset === p.id }"
              @click="scenarioPreset = p.id"
            >
              <span class="preset-label">{{ p.label }}</span>
              <span class="preset-desc">{{ p.desc }}</span>
            </button>
          </div>
        </div>

        <p v-if="scenarioError" class="scenario-error" data-testid="scenario-error">{{ scenarioError }}</p>

        <button
          class="btn btn-primary launch-button scenario-launch-btn"
          :class="{ loading: scenarioIsLoading }"
          :disabled="scenarioIsLoading"
          data-testid="scenario-compare-button"
          @click="handleScenarioCompare"
        >
          <span v-if="scenarioIsLoading" class="spinner"></span>
          {{ scenarioIsLoading ? '作成中...' : 'シナリオ比較を開始' }}
        </button>
      </div>
    </section>

    <!-- History -->
    <section class="section">
      <div class="section-header">
        <h3 class="section-title">実行履歴</h3>
        <span v-if="recentSimulations.length > 0" class="section-badge">{{ recentSimulations.length }} 件</span>
      </div>
      <div v-if="recentSimulations.length === 0" class="empty-state">
        <p class="empty-state-text">まだ分析がありません</p>
        <p class="empty-state-hint">上のテンプレートを選んで、最初の質問を投げてみましょう</p>
      </div>
      <div v-else class="history-list">
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
            <span class="status-badge" :class="getStatusColor(sim.status)">{{ getStatusLabel(sim.status) }}</span>
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
  padding: clamp(2.5rem, 5vw, 4rem) 0 var(--space-6);
}

.hero-title {
  font-size: var(--text-3xl);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.2;
  background: linear-gradient(180deg, #fff 30%, rgba(255,255,255,0.7) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-desc {
  margin: 0.85rem auto 0;
  font-size: clamp(0.88rem, 0.4vw + 0.8rem, 0.96rem);
  color: var(--text-secondary);
  max-width: 38rem;
  line-height: 1.65;
}

/* How It Works (collapsible) */
.how-it-works {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-card);
}

.how-it-works-summary {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  color: var(--text-muted);
  cursor: pointer;
  list-style: none;
}

.how-it-works-summary::-webkit-details-marker { display: none; }
.how-it-works-summary::before { content: '+ '; font-family: var(--font-mono); }
.how-it-works[open] .how-it-works-summary::before { content: '- '; }

.phase-workflow {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: 0 var(--space-4) var(--space-4);
}

.phase-step {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}

.phase-num {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--accent);
  margin-right: var(--space-2);
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: var(--space-8) var(--space-4);
}

.empty-state-text {
  font-size: var(--text-base);
  color: var(--text-secondary);
  margin-bottom: var(--space-2);
}

.empty-state-hint {
  font-size: var(--text-sm);
  color: var(--text-muted);
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

/* === Unified Input Section === */
.input-section {
  background: linear-gradient(170deg, rgba(99, 102, 241, 0.04) 0%, var(--bg-card) 40%);
  border: 1px solid rgba(99, 102, 241, 0.12);
  border-radius: 14px;
  padding: 1.75rem 1.5rem;
  position: relative;
}

.input-section::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.5), rgba(139, 92, 246, 0.5), transparent);
  border-radius: 14px 14px 0 0;
}

.input-section-title {
  font-size: 1.15rem;
  font-weight: 700;
  margin-bottom: 0.3rem;
}

.input-section-hint {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-bottom: 1.25rem;
}

.question-templates {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 0.75rem;
}

.question-card {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: var(--panel-padding);
  padding-top: calc(var(--panel-padding) + 4px);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.25s, box-shadow 0.25s;
  text-align: left;
  overflow: hidden;
}

.question-card-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--card-accent, var(--accent));
  border-radius: var(--radius) var(--radius) 0 0;
}

.question-card:hover { border-color: rgba(255,255,255,0.12); }
.question-card.selected { border-color: var(--card-accent, var(--accent)); box-shadow: 0 0 0 1px var(--card-accent, var(--accent)); background: rgba(255, 255, 255, 0.03); }

.question-icon { font-size: 1.1rem; flex-shrink: 0; }

.question-title { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }

/* Wizard Inline */
.wizard-inline {
  margin-top: 1rem;
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius);
  padding: 1rem;
  background: rgba(99, 102, 241, 0.03);
}

.wizard-inline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.wizard-inline-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent, #6366f1);
}

.wizard-clear-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 0 0.25rem;
  line-height: 1;
}

.wizard-clear-btn:hover { color: var(--text-primary); }

.wizard-fields {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.wizard-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

/* Free Prompt */
.free-prompt {
  margin-top: 0.75rem;
}

.free-prompt-label {
  display: block;
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 0.4rem;
}

.prompt-textarea {
  width: 100%;
  background: var(--bg-input, rgba(255,255,255,0.04));
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 6px);
  color: var(--text-primary);
  padding: 0.75rem;
  font-size: 0.88rem;
  line-height: 1.55;
  resize: vertical;
  font-family: inherit;
}

.prompt-textarea:focus {
  outline: none;
  border-color: var(--accent, #6366f1);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15);
}

.prompt-textarea::placeholder { color: var(--text-muted); }

/* File Drop */
.file-drop-details {
  margin-top: 0.5rem;
}

.file-drop-summary {
  font-size: 0.75rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.3rem 0;
}

.file-drop-summary:hover { color: var(--text-secondary); }

/* Preset Selection */
.preset-section { margin-top: 1.5rem; }
.preset-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 0.75rem;
}
.preset-cards {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.25rem;
}
.preset-card {
  flex: 1;
  min-width: 120px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
  padding: 0.75rem;
  background: var(--card-bg, #18181b);
  border: 1px solid var(--border-subtle, #27272a);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  text-align: left;
}
.preset-card:hover {
  border-color: var(--text-muted, #71717a);
}
.preset-card.selected {
  border-color: #6366f1;
  box-shadow: 0 0 0 1px #6366f1, 0 2px 8px rgba(99, 102, 241, 0.2);
}
.preset-label {
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text-primary, #fafafa);
}
.preset-card.selected .preset-label { color: #a5b4fc; }
.preset-desc {
  font-size: 0.65rem;
  color: var(--text-muted, #a1a1aa);
  line-height: 1.3;
}
.preset-meta {
  font-size: 0.6rem;
  color: var(--text-muted, #71717a);
  margin-top: auto;
}

.preset-card.recommended {
  border-color: rgba(99, 102, 241, 0.3);
  background: rgba(99, 102, 241, 0.06);
  position: relative;
}

.preset-recommended {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  font-weight: 700;
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.18);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 999px;
  padding: 0.08rem 0.45rem;
  letter-spacing: 0.04em;
  align-self: flex-start;
}

/* Launch */
.launch-button {
  width: 100%;
  margin-top: 1.25rem;
  padding: 0.9rem 1.5rem;
  font-size: 1rem;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  border-radius: 10px;
  color: #fff;
  cursor: pointer;
  transition: box-shadow 0.3s, transform 0.15s;
  letter-spacing: 0.02em;
}

.launch-button:hover:not(:disabled) {
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4), 0 0 40px rgba(139, 92, 246, 0.15);
  transform: translateY(-1px);
}

.launch-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.launch-note {
  text-align: center;
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-top: 0.6rem;
  letter-spacing: 0.01em;
}

/* Legacy wizard-form (kept for compat) */
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

/* legacy launch-section removed — now inline in input-section */

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

/* === Scenario Comparison Section === */
.scenario-section {
  background: var(--bg-card);
  border: 1px solid rgba(245, 158, 11, 0.18);
  border-radius: 14px;
  padding: 1.75rem 1.5rem;
  position: relative;
  overflow: hidden;
}

.scenario-header {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}

.scenario-accent-bar {
  width: 4px;
  min-height: 2.5rem;
  background: var(--warning, #f59e0b);
  border-radius: 2px;
  flex-shrink: 0;
}

.scenario-title {
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.scenario-desc {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin-top: 0.2rem;
  line-height: 1.5;
}

.scenario-form {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.scenario-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.scenario-textarea {
  font-family: var(--font-mono, monospace);
  font-size: 0.8rem;
  line-height: 1.5;
}

.scenario-select {
  appearance: auto;
  cursor: pointer;
}

.scenario-no-pop {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.scenario-no-pop a {
  color: var(--accent);
  text-decoration: underline;
}

.scenario-error {
  font-size: 0.78rem;
  color: var(--danger, #ef4444);
  padding: 0.4rem 0.6rem;
  background: rgba(239, 68, 68, 0.08);
  border-radius: var(--radius-sm, 6px);
}

.scenario-launch-btn {
  background: linear-gradient(135deg, #f59e0b, #f97316);
}

.scenario-launch-btn:hover:not(:disabled) {
  box-shadow: 0 4px 20px rgba(245, 158, 11, 0.4), 0 0 40px rgba(249, 115, 22, 0.15);
}
</style>
