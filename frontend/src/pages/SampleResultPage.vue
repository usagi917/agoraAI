<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import { getSampleResult } from '../api/client'
import { useForceGraph } from '../composables/useForceGraph'

const route = useRoute()
const sampleId = route.params.id as string

const sample = ref<any>(null)
const report = ref<any>(null)
const error = ref('')
const loading = ref(true)
const graphContainer = ref<HTMLElement | null>(null)
const activeTab = ref<'report' | 'pm_board'>('report')

const { setFullGraph, graphError } = useForceGraph(graphContainer)

const isPmBoardMode = computed(() => sample.value?.mode === 'pm_board')

function renderMarkdown(content: string): string {
  return content
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^---$/gm, '<hr/>')
    .replace(/\n\n/g, '</p><p>')
}

onMounted(async () => {
  try {
    const data = await getSampleResult(sampleId)
    sample.value = data
    report.value = data.report

    if (isPmBoardMode.value) {
      activeTab.value = 'pm_board'
    }

    if (data.graph?.nodes?.length) {
      await nextTick()
      setFullGraph(data.graph.nodes, data.graph.edges)
    }
  } catch (e) {
    error.value = 'サンプルデータの読み込みに失敗しました。'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="results-page">
    <div v-if="loading" class="loading-state">
      <div class="loading-dots"><span></span><span></span><span></span></div>
      <p>読み込み中...</p>
    </div>

    <template v-else>
      <!-- Header -->
      <div class="result-header">
        <div class="header-left">
          <h2>Sample Results</h2>
          <span v-if="sample" class="header-meta">
            <span class="mode-tag">{{ sample.mode.toUpperCase() }}</span>
            <span class="sample-badge">SAMPLE</span>
            {{ sample.template_name || 'プロンプト実行' }} · {{ sample.execution_profile }}
          </span>
          <p v-if="sample" class="header-prompt">{{ sample.prompt_text }}</p>
        </div>
        <div class="header-actions">
          <router-link to="/" class="btn btn-ghost">新規分析を開始</router-link>
        </div>
      </div>

      <div v-if="error" class="error-banner">{{ error }}</div>

      <!-- Tabs -->
      <div class="tab-bar">
        <button
          v-if="!isPmBoardMode"
          class="tab-btn"
          :class="{ active: activeTab === 'report' }"
          @click="activeTab = 'report'"
        >
          レポート
        </button>
        <button
          v-if="isPmBoardMode"
          class="tab-btn"
          :class="{ active: activeTab === 'pm_board' }"
          @click="activeTab = 'pm_board'"
        >
          PM Board
        </button>
      </div>

      <div class="results-layout">
        <!-- Left: Main Content -->
        <div class="results-main">
          <!-- Report tab (single mode) -->
          <div v-if="activeTab === 'report'" class="tab-panel">
            <div v-if="report?.content" class="report-panel">
              <div class="report-content" v-html="renderMarkdown(report.content)"></div>
            </div>
            <div v-else class="empty-state">レポートが見つかりません</div>
          </div>

          <!-- PM Board tab -->
          <div v-if="activeTab === 'pm_board' && report" class="tab-panel">
            <div class="pm-board-result">
              <template v-if="report.sections">
                <div v-if="report.sections.core_question" class="pm-section">
                  <h3 class="pm-section-title">1. 核心質問</h3>
                  <p class="pm-section-content">{{ report.sections.core_question }}</p>
                </div>

                <div v-if="report.sections.assumptions?.length" class="pm-section">
                  <h3 class="pm-section-title">2. 前提条件</h3>
                  <div v-for="(a, i) in report.sections.assumptions" :key="i" class="pm-card">
                    <div class="pm-card-header">
                      <span class="pm-card-label">{{ a.assumption }}</span>
                      <span class="pm-confidence" :style="{ color: a.confidence > 0.7 ? 'var(--success)' : a.confidence > 0.4 ? 'var(--warning, #f59e0b)' : 'var(--danger)' }">
                        {{ (a.confidence * 100).toFixed(0) }}%
                      </span>
                    </div>
                    <p v-if="a.evidence" class="pm-card-detail">根拠: {{ a.evidence }}</p>
                    <p v-if="a.impact_if_wrong" class="pm-card-detail pm-risk">誤りの影響: {{ a.impact_if_wrong }}</p>
                  </div>
                </div>

                <div v-if="report.sections.uncertainties?.length" class="pm-section">
                  <h3 class="pm-section-title">3. 不確実性</h3>
                  <div v-for="(u, i) in report.sections.uncertainties" :key="i" class="pm-card">
                    <div class="pm-card-header">
                      <span class="pm-card-label">{{ u.uncertainty }}</span>
                      <span class="pm-risk-badge" :class="'risk-' + u.risk_level">{{ u.risk_level }}</span>
                    </div>
                    <p v-if="u.validation_method" class="pm-card-detail">検証方法: {{ u.validation_method }}</p>
                  </div>
                </div>

                <div v-if="report.sections.risks?.length" class="pm-section">
                  <h3 class="pm-section-title">4. リスク</h3>
                  <div v-for="(r, i) in report.sections.risks" :key="i" class="pm-card">
                    <div class="pm-card-header">
                      <span class="pm-card-label">{{ r.risk }}</span>
                      <span class="pm-confidence">{{ (r.probability * 100).toFixed(0) }}%</span>
                    </div>
                    <p v-if="r.mitigation" class="pm-card-detail">緩和策: {{ r.mitigation }}</p>
                  </div>
                </div>

                <div v-if="report.sections.winning_hypothesis?.if_true" class="pm-section">
                  <h3 class="pm-section-title">5. 勝利仮説</h3>
                  <div class="pm-card pm-highlight">
                    <p><strong>IF</strong> {{ report.sections.winning_hypothesis.if_true }}</p>
                    <p><strong>THEN</strong> {{ report.sections.winning_hypothesis.then_do }}</p>
                    <p><strong>TO ACHIEVE</strong> {{ report.sections.winning_hypothesis.to_achieve }}</p>
                    <span class="pm-confidence">
                      確信度: {{ ((report.sections.winning_hypothesis.confidence || 0) * 100).toFixed(0) }}%
                    </span>
                  </div>
                </div>

                <div v-if="report.sections.customer_validation_plan?.key_questions?.length" class="pm-section">
                  <h3 class="pm-section-title">6. 顧客検証計画</h3>
                  <div class="pm-card">
                    <p v-if="report.sections.customer_validation_plan.target_segments?.length">
                      <strong>ターゲット:</strong> {{ report.sections.customer_validation_plan.target_segments.join(', ') }}
                    </p>
                    <ul>
                      <li v-for="(q, i) in report.sections.customer_validation_plan.key_questions" :key="i">{{ q }}</li>
                    </ul>
                    <p v-if="report.sections.customer_validation_plan.success_criteria">
                      <strong>成功基準:</strong> {{ report.sections.customer_validation_plan.success_criteria }}
                    </p>
                  </div>
                </div>

                <div v-if="report.sections.market_view?.market_size" class="pm-section">
                  <h3 class="pm-section-title">7. 市場/競合ビュー</h3>
                  <div class="pm-card">
                    <p><strong>市場規模:</strong> {{ report.sections.market_view.market_size }}</p>
                    <p v-if="report.sections.market_view.growth_rate"><strong>成長率:</strong> {{ report.sections.market_view.growth_rate }}</p>
                    <div v-if="report.sections.market_view.key_players?.length">
                      <strong>主要プレイヤー:</strong>
                      <div v-for="(p, i) in report.sections.market_view.key_players" :key="i" class="pm-player">
                        {{ p.name }} — {{ p.position }}
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="report.sections.gtm_hypothesis?.value_proposition" class="pm-section">
                  <h3 class="pm-section-title">8. GTM仮説</h3>
                  <div class="pm-card">
                    <p><strong>ターゲット:</strong> {{ report.sections.gtm_hypothesis.target_customer }}</p>
                    <p><strong>価値提案:</strong> {{ report.sections.gtm_hypothesis.value_proposition }}</p>
                    <p v-if="report.sections.gtm_hypothesis.channel"><strong>チャネル:</strong> {{ report.sections.gtm_hypothesis.channel }}</p>
                    <p v-if="report.sections.gtm_hypothesis.pricing_model"><strong>価格モデル:</strong> {{ report.sections.gtm_hypothesis.pricing_model }}</p>
                  </div>
                </div>

                <div v-if="report.sections.mvp_scope?.in_scope?.length" class="pm-section">
                  <h3 class="pm-section-title">9. MVPスコープ</h3>
                  <div class="pm-card">
                    <div class="pm-scope-columns">
                      <div>
                        <strong>In Scope:</strong>
                        <ul><li v-for="(s, i) in report.sections.mvp_scope.in_scope" :key="i">{{ s }}</li></ul>
                      </div>
                      <div>
                        <strong>Out of Scope:</strong>
                        <ul><li v-for="(s, i) in report.sections.mvp_scope.out_of_scope" :key="i">{{ s }}</li></ul>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="report.sections.plan_30_60_90?.day_30" class="pm-section">
                  <h3 class="pm-section-title">10. 30/60/90日計画</h3>
                  <div class="pm-timeline-grid">
                    <div v-for="period in ['day_30', 'day_60', 'day_90']" :key="period" class="pm-card">
                      <h4 class="pm-period-label">{{ period === 'day_30' ? '30日' : period === 'day_60' ? '60日' : '90日' }}</h4>
                      <div v-if="report.sections.plan_30_60_90[period]?.goals?.length">
                        <strong>目標:</strong>
                        <ul><li v-for="(g, i) in report.sections.plan_30_60_90[period].goals" :key="i">{{ g }}</li></ul>
                      </div>
                      <div v-if="report.sections.plan_30_60_90[period]?.actions?.length">
                        <strong>アクション:</strong>
                        <ul><li v-for="(a, i) in report.sections.plan_30_60_90[period].actions" :key="i">{{ a }}</li></ul>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="report.sections.top_5_actions?.length" class="pm-section">
                  <h3 class="pm-section-title">11. 今すぐやるべき5アクション</h3>
                  <div v-for="(action, idx) in report.sections.top_5_actions" :key="idx" class="pm-card pm-action">
                    <div class="pm-action-header">
                      <span class="pm-action-number">{{ Number(idx) + 1 }}</span>
                      <span class="pm-card-label">{{ action.action }}</span>
                      <span v-if="action.confidence" class="pm-confidence">{{ (action.confidence * 100).toFixed(0) }}%</span>
                    </div>
                    <p v-if="action.owner" class="pm-card-detail">担当: {{ action.owner }}</p>
                    <p v-if="action.deadline" class="pm-card-detail">期限: {{ action.deadline }}</p>
                    <p v-if="action.evidence" class="pm-card-detail">根拠: {{ action.evidence }}</p>
                  </div>
                </div>
              </template>

              <div v-if="report.contradictions?.length" class="pm-section">
                <h3 class="pm-section-title">矛盾検出</h3>
                <div v-for="(c, i) in report.contradictions" :key="i" class="pm-card pm-contradiction">
                  <p><strong>{{ c.between?.join(' vs ') }}:</strong> {{ c.issue }}</p>
                  <p class="pm-card-detail">解決案: {{ c.resolution }}</p>
                </div>
              </div>

              <div v-if="report.overall_confidence" class="pm-overall">
                <span>総合確信度:</span>
                <span class="pm-overall-score">{{ (report.overall_confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Right: Side Panel -->
        <div class="results-side">
          <!-- 3D Graph -->
          <div v-if="sample?.graph?.nodes?.length" class="side-card">
            <div class="side-header">
              <h3>3D Graph</h3>
            </div>
            <div ref="graphContainer" class="graph-snapshot"></div>
            <div v-if="graphError" class="graph-error-note">{{ graphError }}</div>
          </div>

          <!-- Sample Info -->
          <div class="side-card">
            <div class="side-header">
              <h3>About this Sample</h3>
            </div>
            <p class="sample-info-text">
              これはAgent AIのデモ用サンプル結果です。実際の分析を実行するには、ホームページから新規シミュレーションを開始してください。
            </p>
            <router-link to="/" class="btn btn-primary sample-cta-btn">
              新規分析を開始
            </router-link>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.results-page { display: flex; flex-direction: column; gap: var(--section-gap); }

.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 400px; gap: 1rem; color: var(--text-muted); }
.loading-dots { display: flex; gap: 4px; }
.loading-dots span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: typing-dot 1.4s ease-in-out infinite; }
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
  padding: var(--panel-padding);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.result-header h2 { font-size: 1.1rem; font-weight: 700; }
.header-left {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.header-meta {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.header-prompt {
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.mode-tag { font-family: var(--font-mono); font-size: 0.6rem; font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 3px; background: var(--accent-subtle); color: var(--accent); }

.sample-badge {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  font-weight: 700;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.header-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; justify-content: flex-end; }
.btn-ghost { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.5rem 1rem; background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-secondary); font-family: var(--font-sans); font-size: 0.82rem; font-weight: 500; cursor: pointer; text-decoration: none; transition: all 0.2s; }
.btn-ghost:hover { border-color: rgba(255,255,255,0.12); color: var(--text-primary); }

.error-banner { padding: 0.75rem 1.25rem; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); border-radius: var(--radius-sm); color: var(--danger); font-size: 0.85rem; }

.tab-bar { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.tab-btn { padding: 0.6rem 1.2rem; background: transparent; border: 1px solid var(--border); border-bottom: none; border-radius: var(--radius-sm) var(--radius-sm) 0 0; color: var(--text-muted); font-family: var(--font-sans); font-size: 0.82rem; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.tab-btn.active { background: var(--bg-card); color: var(--accent); }

.results-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(18rem, 22rem);
  gap: 1rem;
  align-items: start;
}

.results-main {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 0 var(--radius) var(--radius) var(--radius);
  padding: clamp(1rem, 1vw + 0.8rem, 2rem) clamp(1rem, 2vw, 2.5rem);
  min-height: min(70vh, 32rem);
  min-width: 0;
}

.tab-panel { animation: fade-in 0.3s ease; }

.report-panel { display: flex; flex-direction: column; gap: 1rem; }
.report-content { max-width: 720px; line-height: 1.85; font-size: 0.9rem; user-select: text; -webkit-user-select: text; }
.report-content :deep(h2) { font-size: 1.25rem; font-weight: 700; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }
.report-content :deep(h3) { font-size: 1.05rem; font-weight: 600; margin: 1.5rem 0 0.75rem; }
.report-content :deep(h4) { font-size: 0.92rem; font-weight: 600; margin: 1rem 0 0.5rem; color: var(--text-secondary); }
.report-content :deep(li) { margin-left: 1.5rem; margin-bottom: 0.4rem; }
.report-content :deep(strong) { font-weight: 600; }
.report-content :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 2rem 0; }

.empty-state { text-align: center; padding: 3rem; color: var(--text-muted); font-size: 0.85rem; }

.results-side { display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; }
.side-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: var(--panel-padding); }
.side-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; gap: 0.75rem; flex-wrap: wrap; }
.side-header h3 { font-size: 0.82rem; font-weight: 600; }

.graph-snapshot {
  height: clamp(14rem, 26vw, 18rem);
  background: radial-gradient(ellipse at 30% 40%, #0d0d2b 0%, #060614 50%, #020208 100%);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(100,100,255,0.12);
  margin-bottom: 0.5rem;
}
.graph-error-note {
  margin-bottom: 0.5rem;
  padding: 0.75rem 0.9rem;
  border: 1px solid rgba(245,158,11,0.24);
  border-radius: var(--radius-sm);
  background: rgba(245,158,11,0.08);
  color: var(--text-secondary);
  font-size: 0.8rem;
  line-height: 1.6;
}

.sample-info-text {
  font-size: 0.82rem;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 1rem;
}

.sample-cta-btn {
  width: 100%;
  text-align: center;
  text-decoration: none;
  display: block;
  padding: 0.6rem 1rem;
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  font-weight: 500;
}

/* PM Board styles */
.pm-board-result { display: flex; flex-direction: column; gap: 1.5rem; }
.pm-section-title { font-size: 0.95rem; font-weight: 600; margin-bottom: 0.75rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--border); }
.pm-section-content { font-size: 1.1rem; font-weight: 500; line-height: 1.6; }
.pm-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem 1rem; margin-bottom: 0.5rem; }
.pm-card-header { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; margin-bottom: 0.3rem; }
.pm-card-label { font-size: 0.88rem; font-weight: 500; }
.pm-card-detail { font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.25rem; }
.pm-risk { color: var(--danger); }
.pm-confidence { font-family: var(--font-mono); font-size: 0.78rem; font-weight: 600; color: var(--accent); }
.pm-risk-badge { font-family: var(--font-mono); font-size: 0.68rem; font-weight: 600; padding: 0.1rem 0.4rem; border-radius: 3px; text-transform: uppercase; }
.pm-risk-badge.risk-high { background: rgba(239,68,68,0.15); color: var(--danger); }
.pm-risk-badge.risk-medium { background: rgba(245,158,11,0.15); color: #f59e0b; }
.pm-risk-badge.risk-low { background: rgba(34,197,94,0.15); color: var(--success); }
.pm-highlight { border-color: var(--accent); background: rgba(99,102,241,0.05); }
.pm-highlight p { margin: 0.3rem 0; font-size: 0.88rem; }
.pm-scope-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.pm-timeline-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.75rem; }
.pm-period-label { font-family: var(--font-mono); font-size: 0.85rem; font-weight: 600; color: var(--accent); margin-bottom: 0.5rem; }
.pm-action { display: flex; flex-direction: column; gap: 0.2rem; }
.pm-action-header { display: flex; align-items: center; gap: 0.5rem; }
.pm-action-number { width: 24px; height: 24px; border-radius: 50%; background: var(--accent); color: white; display: flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 700; flex-shrink: 0; }
.pm-contradiction { border-left: 3px solid var(--danger); }
.pm-overall { display: flex; align-items: center; gap: 0.75rem; padding: 1rem; background: rgba(99,102,241,0.08); border-radius: var(--radius-sm); font-size: 0.9rem; font-weight: 500; }
.pm-overall-score { font-family: var(--font-mono); font-size: 1.5rem; font-weight: 700; color: var(--accent); }
.pm-player { font-size: 0.82rem; color: var(--text-secondary); padding-left: 0.5rem; margin: 0.2rem 0; }

@media (max-width: 900px) {
  .results-layout {
    grid-template-columns: 1fr;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .result-header {
    gap: 0.75rem;
  }

  .tab-btn {
    width: 100%;
    border-bottom: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .results-main {
    border-radius: var(--radius);
    min-height: auto;
  }

  .graph-snapshot {
    height: 14rem;
  }

  .pm-scope-columns {
    grid-template-columns: 1fr;
  }
}
</style>
