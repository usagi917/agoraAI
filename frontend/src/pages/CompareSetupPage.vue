<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listPopulations } from '../api/client'
import { useScenarioPairStore } from '../stores/scenarioPairStore'

const router = useRouter()
const scenarioPairStore = useScenarioPairStore()

const populations = ref<Array<{ id: string; agent_count: number; status: string }>>([])
const selectedPopulationId = ref('')
const decisionContext = ref('')

const policyType = ref('住宅補助金')
const amount = ref('月3万円')
const targetPopulation = ref('年収400万円以下')
const duration = ref('12ヶ月')

const selectedPreset = ref('standard')
const presets = [
  { id: 'quick', label: 'Quick', desc: '社会反応 → レポート', time: '約1分' },
  { id: 'standard', label: 'Standard', desc: '社会反応 → 評議会 → レポート', time: '約3分' },
  { id: 'deep', label: 'Deep', desc: '全フェーズ投入・最高品質', time: '約8分' },
  { id: 'research', label: 'Research', desc: 'イシュー深掘り＋介入テスト', time: '約10分' },
]

const isLoading = ref(false)
const error = ref('')
const loadError = ref('')

onMounted(async () => {
  try {
    const pops = await listPopulations()
    populations.value = pops
    if (pops.length > 0) {
      selectedPopulationId.value = pops[0].id
    }
  } catch {
    loadError.value = '母集団の取得に失敗しました'
  }
})

async function handleSubmit() {
  error.value = ''

  if (!decisionContext.value.trim()) {
    error.value = '比べたいテーマを入力してください'
    return
  }
  if (!selectedPopulationId.value) {
    error.value = '母集団を選択してください'
    return
  }

  isLoading.value = true
  try {
    const interventionParams = {
      policy_type: policyType.value,
      amount: amount.value,
      target_population: targetPopulation.value,
      duration: duration.value,
    }
    const pair = await scenarioPairStore.createScenarioPair({
      population_id: selectedPopulationId.value,
      decision_context: decisionContext.value.trim(),
      intervention_params: interventionParams,
      preset: selectedPreset.value,
    })
    router.push(`/scenario/${pair.id}`)
  } catch {
    error.value = scenarioPairStore.error || '2条件比較の作成に失敗しました'
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <div class="compare-setup-page">
    <section class="page-header">
      <h2 class="page-title">2つの条件を比べる</h2>
      <p class="page-desc">同じ母集団で、「介入なし」と「介入あり」を見比べます</p>
    </section>

    <div v-if="loadError" class="notice error">{{ loadError }}</div>

    <div v-else-if="populations.length === 0" class="notice info">
      <p>母集団がありません。先に母集団を作成してください。</p>
      <router-link to="/populations" class="btn btn-primary notice-btn">母集団を作成 →</router-link>
    </div>

    <form v-else class="compare-form" @submit.prevent="handleSubmit">
      <div class="form-group">
        <label class="form-label" for="decision-context">比べたいテーマ</label>
        <input
          id="decision-context"
          v-model="decisionContext"
          class="form-input"
          type="text"
          placeholder="例: 住宅補助金制度を導入したらどうなるか"
          data-testid="compare-decision-context"
        />
      </div>

      <fieldset class="form-fieldset">
        <legend class="form-legend">介入ありの条件</legend>
        <div class="param-grid">
          <div class="form-group">
            <label class="form-label" for="policy-type">施策の種類</label>
            <input
              id="policy-type"
              v-model="policyType"
              class="form-input"
              type="text"
              placeholder="例: 住宅補助金"
              data-testid="compare-policy-type"
            />
          </div>
          <div class="form-group">
            <label class="form-label" for="amount">規模・金額</label>
            <input
              id="amount"
              v-model="amount"
              class="form-input"
              type="text"
              placeholder="例: 月3万円"
              data-testid="compare-amount"
            />
          </div>
          <div class="form-group">
            <label class="form-label" for="target-population">対象者</label>
            <input
              id="target-population"
              v-model="targetPopulation"
              class="form-input"
              type="text"
              placeholder="例: 年収400万円以下"
              data-testid="compare-target-population"
            />
          </div>
          <div class="form-group">
            <label class="form-label" for="duration">期間</label>
            <input
              id="duration"
              v-model="duration"
              class="form-input"
              type="text"
              placeholder="例: 12ヶ月"
              data-testid="compare-duration"
            />
          </div>
        </div>
      </fieldset>

      <div class="form-group">
        <label class="form-label" for="population-select">母集団</label>
        <select
          id="population-select"
          v-model="selectedPopulationId"
          class="form-input form-select"
          data-testid="compare-population-select"
        >
          <option v-for="pop in populations" :key="pop.id" :value="pop.id">
            {{ pop.id.slice(0, 8) }}... ({{ pop.agent_count }}人)
          </option>
        </select>
      </div>

      <div class="form-group">
        <span class="form-label">分析モード</span>
        <div class="preset-cards">
          <button
            v-for="p in presets"
            :key="p.id"
            type="button"
            class="preset-card"
            :class="{ selected: selectedPreset === p.id, recommended: p.id === 'standard' }"
            :data-testid="`compare-preset-${p.id}`"
            @click="selectedPreset = p.id"
          >
            <span v-if="p.id === 'standard'" class="preset-recommended">おすすめ</span>
            <span class="preset-label">{{ p.label }}</span>
            <span class="preset-desc">{{ p.desc }}</span>
            <span class="preset-meta">{{ p.time }}</span>
          </button>
        </div>
      </div>

      <p v-if="error" class="form-error" data-testid="compare-error">{{ error }}</p>

      <button
        type="submit"
        class="submit-button"
        :class="{ loading: isLoading }"
        :disabled="isLoading"
        data-testid="compare-submit-button"
      >
        <span v-if="isLoading" class="spinner"></span>
        {{ isLoading ? '作成中...' : 'この条件で比較する' }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.compare-setup-page {
  display: flex;
  flex-direction: column;
  gap: clamp(1.25rem, 1vw + 1rem, 2rem);
  max-width: 720px;
}

.page-header {
  padding-top: 1rem;
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: 800;
  letter-spacing: -0.03em;
}

.page-desc {
  margin-top: 0.4rem;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.notice {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--panel-padding);
  background: var(--bg-card);
  font-size: var(--text-sm);
}

.notice.error {
  border-color: rgba(239, 68, 68, 0.35);
  background: rgba(239, 68, 68, 0.08);
  color: var(--danger);
}

.notice.info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  color: var(--text-secondary);
}

.notice-btn {
  flex-shrink: 0;
}

.compare-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1.75rem 1.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.form-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
}

.form-input {
  padding: 0.6rem 0.8rem;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: var(--text-sm);
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-subtle);
}

.form-input::placeholder {
  color: var(--text-muted);
}

.form-select {
  appearance: auto;
  cursor: pointer;
}

.form-fieldset {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.form-legend {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-secondary);
  padding: 0 0.4rem;
}

.param-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr));
  gap: 0.75rem;
}

.preset-cards {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.25rem;
  margin-top: 0.35rem;
}

.preset-card {
  flex: 1;
  min-width: 110px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
  padding: 0.75rem;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
  text-align: left;
}

.preset-card:hover { border-color: var(--text-muted); }

.preset-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent), 0 2px 8px var(--accent-glow);
}

.preset-card.recommended {
  border-color: var(--border-active);
  background: var(--accent-subtle);
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
  align-self: flex-start;
}

.preset-label {
  font-weight: 700;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.preset-card.selected .preset-label { color: var(--accent-hover); }

.preset-desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
  line-height: 1.3;
}

.preset-meta {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: auto;
}

.form-error {
  font-size: var(--text-sm);
  color: var(--danger);
  padding: 0.4rem 0.6rem;
  background: rgba(239, 68, 68, 0.08);
  border-radius: var(--radius-sm);
}

.submit-button {
  width: 100%;
  padding: 0.9rem 1.5rem;
  font-size: 1rem;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--highlight));
  border: none;
  border-radius: var(--radius-lg);
  color: #fff;
  cursor: pointer;
  transition: box-shadow 0.3s, transform 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.submit-button:hover:not(:disabled) {
  box-shadow: 0 4px 20px var(--accent-glow), 0 0 40px var(--highlight-glow);
  transform: translateY(-1px);
}

.submit-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .compare-form {
    padding: 1.25rem 1rem;
  }

  .param-grid {
    grid-template-columns: 1fr;
  }
}
</style>
