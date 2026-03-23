<script setup lang="ts">
import { computed } from 'vue'

import type { DecisionBrief as DecisionBriefType } from '../api/client'

const props = defineProps<{
  brief: DecisionBriefType
}>()

const scoreLabel = computed(() => (
  props.brief.agreement_breakdown ? '合意スコア' : '判断スコア'
))
const scoreValue = computed(() => (
  typeof props.brief.agreement_score === 'number' ? props.brief.agreement_score : null
))
const agreementBreakdown = computed(() => props.brief.agreement_breakdown || null)
const optionComparison = computed(() => props.brief.option_comparison || [])
const recommendedActions = computed(() => props.brief.recommended_actions || [])
const guardrails = computed(() => props.brief.guardrails || [])
const dealBreakers = computed(() => props.brief.deal_breakers || [])
const criticalUnknowns = computed(() => props.brief.critical_unknowns || [])
const nextDecisions = computed(() => props.brief.next_decisions || [])
const keyReasons = computed(() => props.brief.key_reasons || [])
const timeHorizonEntries = computed(() => (
  props.brief.time_horizon
    ? Object.values(props.brief.time_horizon)
    : []
))
const stakeholderReactions = computed(() => props.brief.stakeholder_reactions || [])
const evidenceGaps = computed(() => props.brief.evidence_gaps || [])
const legacyOptions = computed(() => props.brief.options || [])
const legacyRisks = computed(() => props.brief.risk_factors || [])
const legacyNextSteps = computed(() => props.brief.next_steps || [])

function recommendationClass(rec: string): string {
  if (rec === 'Go') return 'recommendation-go'
  if (rec === 'No-Go') return 'recommendation-no-go'
  return 'recommendation-conditional'
}

function pct(value?: number | null): string {
  return typeof value === 'number' ? (value * 100).toFixed(0) : 'n/a'
}
</script>

<template>
  <div class="decision-brief">
    <div class="brief-hero">
      <div class="hero-main">
        <span
          data-testid="recommendation-badge"
          class="recommendation-badge"
          :class="recommendationClass(brief.recommendation)"
        >
          {{ brief.recommendation }}
        </span>
        <p v-if="brief.decision_summary" class="decision-summary">{{ brief.decision_summary }}</p>
        <p v-if="brief.why_now" class="decision-why-now">
          <span class="why-now-label">Why now</span>
          {{ brief.why_now }}
        </p>
      </div>
      <div v-if="scoreValue !== null" class="agreement-overview">
        <span class="agreement-label">{{ scoreLabel }}</span>
        <span class="agreement-value">{{ pct(scoreValue) }}%</span>
      </div>
    </div>

    <div v-if="brief.confidence_explainer" class="brief-section">
      <h4 class="brief-section-title">確信度の見立て</h4>
      <p class="section-prose">{{ brief.confidence_explainer }}</p>
    </div>

    <div v-if="keyReasons.length" class="brief-section">
      <h4 class="brief-section-title">主な判断根拠</h4>
      <div class="reason-list">
        <div v-for="(item, index) in keyReasons" :key="index" class="reason-card">
          <div class="reason-head">
            <span class="reason-index">{{ index + 1 }}</span>
            <span v-if="typeof item.confidence === 'number'" class="reason-confidence">{{ pct(item.confidence) }}%</span>
          </div>
          <div class="reason-text">{{ item.reason }}</div>
          <div v-if="item.evidence" class="reason-meta">根拠: {{ item.evidence }}</div>
          <div v-if="item.decision_impact" class="reason-meta">判断への効き方: {{ item.decision_impact }}</div>
        </div>
      </div>
    </div>

    <div v-if="guardrails.length" class="brief-section">
      <h4 class="brief-section-title">この判断が成り立つ条件</h4>
      <div class="detail-list">
        <div v-for="(item, index) in guardrails" :key="index" class="detail-card">
          <div class="detail-header">
            <span class="detail-title">{{ item.condition }}</span>
            <span v-if="item.status" class="detail-status">{{ item.status }}</span>
          </div>
          <p v-if="item.why_it_matters" class="detail-body">{{ item.why_it_matters }}</p>
        </div>
      </div>
    </div>

    <div v-if="dealBreakers.length" class="brief-section">
      <h4 class="brief-section-title">判断を覆すトリガー</h4>
      <div class="detail-list">
        <div v-for="(item, index) in dealBreakers" :key="index" class="detail-card detail-card-danger">
          <div class="detail-header">
            <span class="detail-title">{{ item.trigger }}</span>
          </div>
          <p class="detail-body">{{ item.impact }}</p>
          <p v-if="item.recommended_response" class="detail-foot">対応: {{ item.recommended_response }}</p>
        </div>
      </div>
    </div>

    <div v-if="criticalUnknowns.length" class="brief-section">
      <h4 class="brief-section-title">追加で潰すべき論点</h4>
      <div class="detail-list">
        <div v-for="(item, index) in criticalUnknowns" :key="index" class="detail-card">
          <div class="detail-header">
            <span class="detail-title">{{ item.question }}</span>
            <span v-if="item.decision_blocking" class="detail-status detail-status-blocking">Blocking</span>
          </div>
          <p v-if="item.importance" class="detail-body">{{ item.importance }}</p>
          <p v-if="item.how_to_validate" class="detail-foot">検証: {{ item.how_to_validate }}</p>
        </div>
      </div>
    </div>

    <div v-if="nextDecisions.length" class="brief-section">
      <h4 class="brief-section-title">次に決めるべきこと</h4>
      <div class="detail-list">
        <div v-for="(item, index) in nextDecisions" :key="index" class="detail-card">
          <div class="detail-header">
            <span class="detail-title">{{ item.decision }}</span>
          </div>
          <p class="detail-foot">
            <span v-if="item.owner">担当: {{ item.owner }}</span>
            <span v-if="item.deadline">期限: {{ item.deadline }}</span>
            <span v-if="item.input_needed">必要入力: {{ item.input_needed }}</span>
          </p>
        </div>
      </div>
    </div>

    <div v-if="recommendedActions.length" class="brief-section">
      <h4 class="brief-section-title">推奨アクション</h4>
      <div class="detail-list">
        <div v-for="(item, index) in recommendedActions" :key="index" class="detail-card">
          <div class="detail-header">
            <span class="detail-title">{{ item.action }}</span>
            <span v-if="item.priority" class="detail-status">{{ item.priority }}</span>
          </div>
          <p class="detail-foot">
            <span v-if="item.owner">担当: {{ item.owner }}</span>
            <span v-if="item.deadline">期限: {{ item.deadline }}</span>
          </p>
          <p v-if="item.expected_learning" class="detail-body">学べること: {{ item.expected_learning }}</p>
        </div>
      </div>
    </div>

    <div v-if="optionComparison.length || legacyOptions.length" class="brief-section">
      <h4 class="brief-section-title">選択肢比較</h4>
      <div class="options-grid">
        <div v-for="(opt, index) in optionComparison" :key="`new-${index}`" class="option-card">
          <div class="option-label">{{ opt.label }}</div>
          <div v-if="opt.upside" class="option-effect">Upside: {{ opt.upside }}</div>
          <div v-if="opt.downside" class="option-risk">Downside: {{ opt.downside }}</div>
          <div v-if="opt.fit" class="option-fit">Fit: {{ opt.fit }}</div>
          <div v-if="opt.when_to_choose" class="option-fit">When: {{ opt.when_to_choose }}</div>
        </div>
        <div v-for="(opt, index) in legacyOptions" :key="`legacy-${index}`" class="option-card">
          <div class="option-label">{{ opt.label }}</div>
          <div class="option-effect">{{ opt.expected_effect }}</div>
          <div class="option-risk">{{ opt.risk }}</div>
        </div>
      </div>
    </div>

    <div v-if="brief.strongest_counterargument" class="brief-section">
      <h4 class="brief-section-title">最強の反論</h4>
      <p class="counterargument-text">{{ brief.strongest_counterargument }}</p>
    </div>

    <div v-if="legacyRisks.length" class="brief-section">
      <h4 class="brief-section-title">リスク要因</h4>
      <div class="risk-list">
        <div v-for="(rf, index) in legacyRisks" :key="index" class="risk-item">
          <span class="risk-condition">{{ rf.condition }}</span>
          <span class="risk-impact">{{ rf.impact }}</span>
        </div>
      </div>
    </div>

    <div v-if="timeHorizonEntries.length" class="brief-section">
      <h4 class="brief-section-title">タイムホライズン</h4>
      <div class="horizon-grid">
        <div v-for="(entry, index) in timeHorizonEntries" :key="index" class="horizon-card">
          <span class="horizon-period">{{ entry.period }}</span>
          <span class="horizon-prediction">{{ entry.prediction }}</span>
        </div>
      </div>
    </div>

    <div v-if="stakeholderReactions.length" class="brief-section">
      <h4 class="brief-section-title">ステークホルダー反応</h4>
      <div class="stakeholder-list">
        <div v-for="(sr, index) in stakeholderReactions" :key="index" class="stakeholder-row">
          <span class="stakeholder-group">{{ sr.group }}</span>
          <span class="stakeholder-reaction">{{ sr.reaction }}</span>
          <div class="stakeholder-bar-track">
            <div class="stakeholder-bar-fill" :style="{ width: sr.percentage + '%' }" />
          </div>
          <span class="stakeholder-pct">{{ sr.percentage }}%</span>
        </div>
      </div>
    </div>

    <div v-if="evidenceGaps.length" class="brief-section">
      <h4 class="brief-section-title">まだ足りない根拠</h4>
      <ul class="next-steps-list">
        <li v-for="(gap, index) in evidenceGaps" :key="index">{{ gap }}</li>
      </ul>
    </div>

    <div v-if="legacyNextSteps.length" class="brief-section">
      <h4 class="brief-section-title">次のステップ</h4>
      <ol class="next-steps-list">
        <li v-for="(step, index) in legacyNextSteps" :key="index">{{ step }}</li>
      </ol>
    </div>

    <div v-if="agreementBreakdown" class="brief-section">
      <h4 class="brief-section-title">合意内訳</h4>
      <div class="breakdown-grid">
        <div class="breakdown-item">
          <span class="breakdown-label">社会</span>
          <span class="breakdown-value">{{ pct(agreementBreakdown.society) }}%</span>
        </div>
        <div class="breakdown-item">
          <span class="breakdown-label">評議会</span>
          <span class="breakdown-value">{{ pct(agreementBreakdown.council) }}%</span>
        </div>
        <div class="breakdown-item">
          <span class="breakdown-label">統合分析</span>
          <span class="breakdown-value">{{ pct(agreementBreakdown.synthesis) }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.decision-brief {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.brief-hero {
  display: flex;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 1.25rem;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.hero-main {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  flex: 1;
}

.recommendation-badge {
  align-self: flex-start;
  font-family: var(--font-mono);
  font-size: 1.3rem;
  font-weight: 700;
  padding: 0.5rem 1.2rem;
  border-radius: var(--radius-sm);
  border: 2px solid;
}

.recommendation-go {
  color: var(--success);
  border-color: rgba(34,197,94,0.4);
  background: rgba(34,197,94,0.1);
}

.recommendation-no-go {
  color: var(--danger);
  border-color: rgba(239,68,68,0.4);
  background: rgba(239,68,68,0.1);
}

.recommendation-conditional {
  color: #f59e0b;
  border-color: rgba(245,158,11,0.4);
  background: rgba(245,158,11,0.1);
}

.decision-summary {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.7;
}

.decision-why-now {
  margin: 0;
  font-size: 0.86rem;
  color: var(--text-secondary);
  line-height: 1.7;
}

.why-now-label {
  display: inline-block;
  margin-right: 0.45rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
}

.agreement-overview {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  align-items: flex-end;
}

.agreement-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.agreement-value {
  font-family: var(--font-mono);
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--accent);
}

.brief-section-title {
  font-size: 0.85rem;
  font-weight: 600;
  margin-bottom: 0.65rem;
  padding-bottom: 0.35rem;
  border-bottom: 1px solid var(--border);
}

.section-prose {
  margin: 0;
  font-size: 0.88rem;
  color: var(--text-secondary);
  line-height: 1.8;
}

.reason-list,
.detail-list,
.risk-list,
.stakeholder-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.reason-card,
.detail-card,
.risk-item,
.horizon-card,
.option-card {
  padding: 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.02);
}

.reason-head,
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.reason-index {
  width: 1.5rem;
  height: 1.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(255,255,255,0.08);
  font-family: var(--font-mono);
  font-size: 0.76rem;
}

.reason-confidence,
.detail-status {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  color: var(--accent);
}

.detail-status-blocking {
  color: var(--danger);
}

.reason-text,
.detail-title {
  font-size: 0.88rem;
  font-weight: 600;
  line-height: 1.6;
}

.reason-meta,
.detail-body,
.detail-foot {
  margin-top: 0.45rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.7;
}

.detail-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.detail-card-danger {
  border-color: rgba(239,68,68,0.25);
  background: rgba(239,68,68,0.04);
}

.breakdown-grid,
.horizon-grid,
.options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
}

.breakdown-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  padding: 0.75rem;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.breakdown-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.breakdown-value {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.option-label {
  font-size: 0.88rem;
  font-weight: 600;
}

.option-effect {
  margin-top: 0.35rem;
  font-size: 0.8rem;
  color: var(--success);
  line-height: 1.6;
}

.option-risk {
  margin-top: 0.35rem;
  font-size: 0.78rem;
  color: var(--danger);
  line-height: 1.6;
}

.option-fit {
  margin-top: 0.35rem;
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.6;
}

.counterargument-text {
  font-size: 0.88rem;
  color: var(--text-secondary);
  line-height: 1.7;
  padding: 0.85rem;
  border-left: 3px solid var(--danger);
  background: rgba(239,68,68,0.05);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  margin: 0;
}

.risk-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.risk-condition {
  font-size: 0.84rem;
  font-weight: 500;
}

.risk-impact {
  font-size: 0.78rem;
  color: var(--danger);
  text-align: right;
}

.horizon-card {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.horizon-period {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent);
}

.horizon-prediction {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.stakeholder-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.stakeholder-group {
  width: 100px;
  font-size: 0.8rem;
  font-weight: 500;
  flex-shrink: 0;
}

.stakeholder-reaction {
  width: 90px;
  font-size: 0.76rem;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.stakeholder-bar-track {
  flex: 1;
  height: 18px;
  background: rgba(255,255,255,0.05);
  border-radius: 3px;
  overflow: hidden;
}

.stakeholder-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.6s ease;
}

.stakeholder-pct {
  width: 40px;
  font-family: var(--font-mono);
  font-size: 0.76rem;
  font-weight: 600;
  text-align: right;
}

.next-steps-list {
  padding-left: 1.4rem;
  font-size: 0.84rem;
  color: var(--text-secondary);
  line-height: 1.8;
}

@media (max-width: 720px) {
  .brief-hero {
    flex-direction: column;
  }

  .agreement-overview {
    align-items: flex-start;
  }

  .detail-foot,
  .stakeholder-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .stakeholder-group,
  .stakeholder-reaction,
  .stakeholder-pct {
    width: auto;
  }

  .risk-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
