<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  getHealth,
  getTemplates,
  createProject,
  uploadDocument,
  createSimulation,
  type HealthResponse,
  type TemplateResponse,
} from '../api/client'
import InputPanel from '../components/InputPanel.vue'

const router = useRouter()

const templates = ref<TemplateResponse[]>([])
const selectedTemplate = ref('')
const selectedProfile = ref('standard')
const selectedPreset = ref('standard')

const analysisModes = [
  { id: 'standard', label: '標準', desc: '社会反応と代表評議会で素早く判断', time: '約3分' },
  { id: 'research', label: '検証強化', desc: '実調査アンカーとシナリオ検証を重視', time: '約10分' },
]
const promptText = ref('')
const files = ref<File[]>([])
const isLoading = ref(false)
const runtimeHealth = ref<HealthResponse | null>(null)
const bootstrapError = ref('')
const examplesOpen = ref(false)
const advancedOpen = ref(false)
// advanced options removed for simplicity

const featuredExample = {
  simulationId: 'db6bbd23-d31c-461c-8e18-6398a44bd4b9',
  category: 'マーケティング調査',
  title: '食生活改善サブスクは、20〜30代の一人暮らしに受け入れられるか？',
  summary: '利用をためらう理由、継続条件、月額1,980円の価格受容性、刺さる訴求を想定顧客へのインタビュー形式で検証した実際の分析結果です。',
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

function syncExamplesDetails(event: Event) {
  examplesOpen.value = event.target instanceof HTMLDetailsElement ? event.target.open : false
}

function syncAdvancedDetails(event: Event) {
  advancedOpen.value = event.target instanceof HTMLDetailsElement ? event.target.open : false
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
  return !hasWizardInput && !hasManualInput
})
const selectedModeInfo = computed(() => (
  analysisModes.find(mode => mode.id === selectedPreset.value) ?? analysisModes[0]
))
// launchLabel は inline で処理

onMounted(async () => {
  try {
    const [health, tmpl] = await Promise.all([getHealth(), getTemplates()])
    runtimeHealth.value = health
    templates.value = tmpl
    if (templates.value.length > 0) {
      selectedTemplate.value = templates.value[0].name
    }
  } catch (error) {
    console.error('Bootstrap error:', error)
    bootstrapError.value = 'バックエンドへの接続に失敗しました。コンテナ起動直後は数秒待って再読み込みしてください。'
  }
})

async function handleLaunch() {
  // Keep duplicate submission protection in the handler so the native
  // disabled attribute does not flip during the click action itself.
  if (isLoading.value || !canLaunchLive.value) return

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

</script>

<template>
  <div class="launchpad-page">
    <!-- Hero -->
    <section class="hero">
      <h2 class="hero-title">ひとつの問いから、<br />社会の反応を予測する</h2>
      <p class="hero-desc">仮想空間でAIが議論し、代表評議会が検証し、あなたの意思決定を支える Decision Brief を生成します。</p>
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
      <p class="input-section-hint">問いを入力すれば、標準分析でそのまま開始できます</p>

      <div class="free-prompt">
        <label class="free-prompt-label" for="launchpad-prompt">分析したい問い</label>
        <textarea
          id="launchpad-prompt"
          name="launchpad-prompt"
          v-model="promptText"
          class="prompt-textarea"
          data-testid="launchpad-prompt"
          placeholder="例: EVバッテリー市場に参入すべきか。顧客受容性、規制リスク、競合反応を知りたい。"
          rows="4"
        />
      </div>

      <details class="example-builder-details" @toggle="syncExamplesDetails">
        <summary class="example-builder-summary">例から作る</summary>
        <div v-if="examplesOpen" class="question-templates">
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
      </details>

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

      <!-- File Upload (compact) -->
      <details class="file-drop-details">
        <summary class="file-drop-summary">ファイルを添付（任意）</summary>
        <InputPanel
          :files="files"
          @update:files="files = $event"
        />
      </details>

      <details class="advanced-details" @toggle="syncAdvancedDetails">
        <summary class="advanced-summary">詳細設定</summary>
        <div v-if="advancedOpen" class="preset-section">
          <h4 class="preset-title">分析モード</h4>
          <div class="preset-cards">
          <button
            v-for="p in analysisModes"
            :key="p.id"
            class="preset-card"
            :class="{ selected: selectedPreset === p.id, recommended: p.id === 'standard' }"
            :data-testid="`preset-${p.id}`"
            @click="selectedPreset = p.id"
          >
            <span v-if="p.id === 'standard'" class="preset-recommended">おすすめ</span>
            <span class="preset-label">{{ p.label }}</span>
            <span class="preset-desc">{{ p.desc }}</span>
            <span class="preset-meta">{{ p.time }}</span>
          </button>
          </div>
        </div>
      </details>

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
        {{ selectedModeInfo?.time ?? '約3分' }}
        — {{ selectedModeInfo?.desc ?? '' }}
      </p>
    </section>

    <!-- How It Works (collapsed) -->
    <details class="how-it-works">
      <summary class="how-it-works-summary">仕組みを見る</summary>
      <div class="phase-workflow">
        <div class="phase-step"><span class="phase-num">01</span><strong>問いを入力</strong> — 自由入力や質問例を選び、必要に応じて根拠文書を添付</div>
        <div class="phase-step"><span class="phase-num">02</span><strong>社会反応を測定</strong> — デジタル住民たちが、意見しスタンスを集約</div>
        <div class="phase-step"><span class="phase-num">03</span><strong>分析モード別に深掘り</strong> — 標準は代表評議会、検証強化は論点抽出と介入比較を実行</div>
        <div class="phase-step"><span class="phase-num">04</span><strong>判断材料を生成</strong> — 進捗をリアルタイムに可視化し、根拠・反対意見・次のアクションを整理</div>
      </div>
    </details>

    <section class="featured-example" aria-labelledby="featured-example-title">
      <div class="featured-example-heading">
        <div>
          <p class="featured-example-eyebrow">実際の分析結果</p>
          <h3 id="featured-example-title" class="featured-example-title">分析事例</h3>
        </div>
        <span class="featured-example-count">1 CASE</span>
      </div>

      <router-link
        :to="`/sim/${featuredExample.simulationId}/results`"
        class="featured-example-card"
        data-testid="featured-example-card"
      >
        <div class="featured-example-body">
          <div class="featured-example-meta">
            <span class="featured-example-status"><span class="featured-example-status-dot" />分析完了</span>
            <span>{{ featuredExample.category }}</span>
            <span>標準分析</span>
          </div>
          <h4 class="featured-example-question">{{ featuredExample.title }}</h4>
          <p class="featured-example-summary">{{ featuredExample.summary }}</p>
        </div>
        <span class="featured-example-link">結果を見る <span aria-hidden="true">→</span></span>
      </router-link>
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

/* Featured example */
.featured-example {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-top: var(--space-4);
}

.featured-example-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
}

.featured-example-eyebrow {
  margin-bottom: 0.25rem;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  letter-spacing: 0.08em;
  color: var(--accent);
}

.featured-example-title {
  font-size: var(--text-xl);
  font-weight: 700;
  letter-spacing: -0.02em;
}

.featured-example-count {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.featured-example-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-6);
  padding: clamp(1.25rem, 2vw, 1.75rem);
  color: var(--text-primary);
  text-decoration: none;
  background:
    radial-gradient(circle at 100% 0, var(--accent-subtle), transparent 44%),
    var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}

.featured-example-card:hover {
  border-color: var(--border-active);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
  transform: translateY(-2px);
}

.featured-example-card:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}

.featured-example-body {
  min-width: 0;
}

.featured-example-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
  flex-wrap: wrap;
}

.featured-example-status {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--success);
}

.featured-example-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 8px var(--success-glow);
}

.featured-example-question {
  max-width: 44rem;
  font-size: clamp(1rem, 0.6vw + 0.9rem, 1.3rem);
  line-height: 1.5;
  letter-spacing: -0.015em;
}

.featured-example-summary {
  max-width: 44rem;
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  line-height: 1.7;
  color: var(--text-secondary);
}

.featured-example-link {
  flex: 0 0 auto;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--accent-hover);
  white-space: nowrap;
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
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.6;
}

.runtime-hint {
  margin-top: 0.6rem;
  font-size: var(--text-xs);
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
.section-note { margin-top: 0.75rem; font-size: 0.78rem; color: var(--text-muted); line-height: 1.6; }
.section-note-warning { color: var(--warning); }
.section-toggle { margin-left: auto; font-size: 0.78rem; }

/* === Unified Input Section === */
.input-section {
  background: linear-gradient(170deg, var(--accent-subtle) 0%, var(--bg-card) 40%);
  border: 1px solid var(--border-active);
  border-radius: var(--radius-lg);
  padding: 1.75rem 1.5rem;
  position: relative;
}

.input-section::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent), var(--highlight), transparent);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
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
  margin-top: 0.75rem;
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
  border: 1px solid var(--border-active);
  border-radius: var(--radius);
  padding: 1rem;
  background: var(--accent-subtle);
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
  color: var(--accent);
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
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-subtle);
}

.prompt-textarea::placeholder { color: var(--text-muted); }

.example-builder-details,
.advanced-details {
  margin-top: 0.75rem;
}

.example-builder-summary,
.advanced-summary {
  font-size: 0.78rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.35rem 0;
}

.example-builder-summary:hover,
.advanced-summary:hover {
  color: var(--text-secondary);
}

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
.preset-section { margin-top: 0.75rem; }
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
  min-width: 180px;
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
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent), 0 2px 8px var(--accent-glow);
}
.preset-label {
  font-weight: 700;
  font-size: 0.85rem;
  color: var(--text-primary, #fafafa);
}
.preset-card.selected .preset-label { color: var(--accent-hover); }
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
  border-color: var(--border-active);
  background: var(--accent-subtle);
  position: relative;
}

.preset-recommended {
  font-family: var(--font-mono);
  font-size: 0.58rem;
  font-weight: 700;
  color: var(--accent-hover);
  background: var(--accent-subtle);
  border: 1px solid var(--border-active);
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
  background: linear-gradient(135deg, var(--accent), var(--highlight));
  border: none;
  border-radius: var(--radius-lg);
  color: #fff;
  cursor: pointer;
  transition: box-shadow 0.3s, transform 0.15s;
  letter-spacing: 0.02em;
}

.launch-button:hover:not(:disabled) {
  box-shadow: 0 4px 20px var(--accent-glow), 0 0 40px var(--highlight-glow);
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
  background: linear-gradient(135deg, var(--accent-subtle), rgba(16,185,129,0.05));
  border: 1px solid var(--border-active);
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

@media (max-width: 900px) {
  .hero {
    padding-top: 1.5rem;
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

  .featured-example-card {
    align-items: flex-start;
    flex-direction: column;
    gap: var(--space-4);
  }

}

</style>
