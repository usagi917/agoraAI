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
const criticalUnknowns = computed(() => (props.brief.critical_unknowns || []).slice(0, 3))
const keyReasons = computed(() => (props.brief.key_reasons || []).slice(0, 3))

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
    <div class="brief-hero" data-testid="brief-hero-card">
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
        <div class="confidence-gauge" data-testid="confidence-gauge">
          <div
            class="confidence-gauge-fill"
            data-testid="confidence-gauge-fill"
            :style="{ width: pct(scoreValue) + '%' }"
          />
        </div>
      </div>
    </div>

    <div v-if="keyReasons.length" class="brief-section" data-testid="section-key-reasons">
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

    <div v-if="criticalUnknowns.length" class="brief-section" data-testid="section-critical-unknowns">
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
  </div>
</template>

<style scoped>
.decision-brief {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.brief-hero {
  display: flex;
  justify-content: space-between;
  gap: var(--space-6);
  padding: var(--space-6);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}

.hero-main {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  flex: 1;
}

.recommendation-badge {
  align-self: flex-start;
  font-family: var(--font-mono);
  font-size: var(--text-xl);
  font-weight: 700;
  padding: var(--space-2) var(--space-4);
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
  font-size: var(--text-base);
  font-weight: 600;
  line-height: 1.7;
}

.decision-why-now {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.7;
}

.why-now-label {
  display: inline-block;
  margin-right: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
}

.agreement-overview {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  align-items: flex-end;
  min-width: 80px;
}

.agreement-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  font-family: var(--font-mono);
}

.agreement-value {
  font-family: var(--font-mono);
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--accent);
}

.confidence-gauge {
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
  margin-top: var(--space-1, 0.25rem);
}

.confidence-gauge-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.6s ease;
}

.brief-section-title {
  font-size: var(--text-sm);
  font-weight: 600;
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}

.section-prose {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.8;
}

.reason-list,
.detail-list,
.risk-list,
.stakeholder-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.reason-card,
.detail-card,
.risk-item,
.horizon-card,
.option-card {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
}

.reason-head,
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
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
  font-size: var(--text-xs);
}

.reason-confidence,
.detail-status {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--accent);
}

.detail-status-blocking {
  color: var(--danger);
}

.reason-text,
.detail-title {
  font-size: var(--text-sm);
  font-weight: 600;
  line-height: 1.6;
}

.reason-meta,
.detail-body,
.detail-foot {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.7;
}

.detail-foot {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
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
  gap: var(--space-3);
}

.breakdown-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-3);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}

.breakdown-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.breakdown-value {
  font-family: var(--font-mono);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.option-label {
  font-size: var(--text-sm);
  font-weight: 600;
}

.option-effect {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--success);
  line-height: 1.6;
}

.option-risk {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--danger);
  line-height: 1.6;
}

.option-fit {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.6;
}

.counterargument-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: 1.7;
  padding: var(--space-4);
  border-left: 3px solid var(--danger);
  background: rgba(239,68,68,0.05);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  margin: 0;
}

.risk-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-4);
}

.risk-condition {
  font-size: var(--text-sm);
  font-weight: 500;
}

.risk-impact {
  font-size: var(--text-xs);
  color: var(--danger);
  text-align: right;
}

.horizon-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.horizon-period {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--accent);
}

.horizon-prediction {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.5;
}

.stakeholder-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.stakeholder-group {
  width: 100px;
  font-size: var(--text-xs);
  font-weight: 500;
  flex-shrink: 0;
}

.stakeholder-reaction {
  width: 90px;
  font-size: var(--text-xs);
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
  font-size: var(--text-xs);
  font-weight: 600;
  text-align: right;
}

.next-steps-list {
  padding-left: var(--space-6);
  font-size: var(--text-sm);
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

@media print {
  .decision-brief { gap: 0.75rem; }
  .brief-hero {
    background: white;
    border: 1px solid #ccc;
    padding: 0.75rem;
  }
  .recommendation-badge {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
  .confidence-gauge {
    background: #e5e5e5;
  }
  .confidence-gauge-fill {
    background: #333;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
  .reason-card,
  .detail-card,
  .option-card,
  .horizon-card,
  .breakdown-item {
    background: white;
    border: 1px solid #ccc;
    break-inside: avoid;
  }
  .stakeholder-bar-track { background: #e5e5e5; }
  .stakeholder-bar-fill {
    background: #333;
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
}
</style>
