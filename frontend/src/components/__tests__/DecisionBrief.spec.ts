import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DecisionBrief from '../DecisionBrief.vue'
import type { DecisionBrief as DecisionBriefType } from '../../api/client'

function makeBrief(overrides: Partial<DecisionBriefType> = {}): DecisionBriefType {
  return {
    recommendation: 'Go',
    agreement_score: 0.82,
    agreement_breakdown: { society: 0.78, council: 0.85, synthesis: 0.83 },
    decision_summary: '市場参入を進めるが、価格仮説の検証を完了するまでは条件を付ける。',
    why_now: '競争環境が動く前に検証順序を固定したい。',
    key_reasons: [
      { reason: '市場成長率が高い', evidence: 'market_view', confidence: 0.84, decision_impact: '需要仮説を補強' },
      { reason: '初期顧客の課題が明確', evidence: 'customer interviews', confidence: 0.76, decision_impact: 'MVP範囲を絞れる' },
    ],
    guardrails: [
      { condition: '価格受容性が成立すること', status: '未検証', why_it_matters: '成立しないと採算が崩れる' },
    ],
    deal_breakers: [
      { trigger: '競合が先に同機能を展開する', impact: '差別化が薄れる', recommended_response: 'ポジショニングを再設計' },
    ],
    critical_unknowns: [
      { question: '価格仮説は成立するか', importance: '最重要', how_to_validate: '5社ヒアリング', decision_blocking: true },
    ],
    next_decisions: [
      { decision: 'パイロットを有料で行うか', owner: 'CEO', deadline: '2週間', input_needed: '価格感度データ' },
    ],
    recommended_actions: [
      { action: '価格ヒアリングを実施', owner: 'CEO', deadline: '2週間', expected_learning: '価格受容性が分かる', priority: 'high' },
      { action: '日報プロトタイプを作成', owner: 'CTO', deadline: '3週間', expected_learning: 'UXの成立性が分かる', priority: 'high' },
    ],
    decision_scorecard: [
      { label: '実行条件', value: 'mode=strict / trust=high_trust / refs=6', detail: 'quality=verified。document=2 / prompt=1 を根拠に構成。' },
      { label: '使いどころ', value: '判断材料として使える', detail: 'guardrails と deal breakers を一緒に確認する。' },
    ],
    option_comparison: [
      { label: '条件付きで進める', upside: '学習を進められる', downside: '速度が落ちる', fit: '不確実性が残る案件', when_to_choose: '主要前提を短期検証できる場合' },
    ],
    confidence_explainer: '市場性は見えているが、価格と定着率の不確実性が残るため中程度の確信度。',
    evidence_gaps: ['価格受容性の一次情報が不足'],
    followup_prompts: [
      '価格仮説は成立するか が解消された場合、recommendation はどう変わるか',
      '競合が先に同機能を展開する が起きた場合の代替案と縮小プランは何か',
    ],
    options: [
      { label: '即時参入', expected_effect: '先行者優位を獲得', risk: '競合の反撃' },
      { label: '段階参入', expected_effect: 'リスク低減', risk: '機会損失' },
    ],
    strongest_counterargument: '市場が成熟しすぎている可能性',
    risk_factors: [
      { condition: '為替変動', impact: '利益率が 5% 低下' },
      { condition: '規制変更', impact: '参入が半年遅延' },
    ],
    next_steps: ['市場調査の深掘り', 'パイロット準備'],
    time_horizon: {
      short_term: { period: '3ヶ月', prediction: '市場調査完了' },
      mid_term: { period: '1年', prediction: '初期顧客獲得' },
      long_term: { period: '3年', prediction: '黒字化達成' },
    },
    stakeholder_reactions: [
      { group: '消費者', reaction: '期待', percentage: 65 },
      { group: '競合', reaction: '警戒', percentage: 80 },
    ],
    ...overrides,
  }
}

describe('DecisionBrief', () => {
  it('renders the recommendation badge', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.get('[data-testid="recommendation-badge"]').text()).toContain('Go')
  })

  it('renders No-Go recommendation', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ recommendation: 'No-Go' }) },
    })
    expect(wrapper.get('[data-testid="recommendation-badge"]').text()).toContain('No-Go')
  })

  it('renders agreement score and breakdown', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    const text = wrapper.text()
    expect(text).toContain('82')
    expect(text).toContain('78')
    expect(text).toContain('85')
    expect(text).toContain('83')
  })

  it('renders options list', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.text()).toContain('条件付きで進める')
    expect(wrapper.text()).toContain('即時参入')
    expect(wrapper.text()).toContain('段階参入')
    expect(wrapper.text()).toContain('先行者優位を獲得')
  })

  it('renders decision-oriented sections', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    const text = wrapper.text()
    expect(text).toContain('市場参入を進めるが')
    expect(text).toContain('価格受容性が成立すること')
    expect(text).toContain('競合が先に同機能を展開する')
    expect(text).toContain('価格ヒアリングを実施')
    expect(text).toContain('判断材料として使える')
    expect(text).toContain('価格受容性の一次情報が不足')
    expect(text).toContain('recommendation はどう変わるか')
  })

  it('renders strongest counterargument', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.text()).toContain('市場が成熟しすぎている可能性')
  })

  it('renders risk factors', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.text()).toContain('為替変動')
    expect(wrapper.text()).toContain('利益率が 5% 低下')
  })

  it('renders time horizon predictions', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.text()).toContain('3ヶ月')
    expect(wrapper.text()).toContain('市場調査完了')
    expect(wrapper.text()).toContain('3年')
    expect(wrapper.text()).toContain('黒字化達成')
  })

  it('renders stakeholder reactions', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.text()).toContain('消費者')
    expect(wrapper.text()).toContain('65')
    expect(wrapper.text()).toContain('競合')
    expect(wrapper.text()).toContain('警戒')
  })

  it('renders next steps', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.text()).toContain('市場調査の深掘り')
    expect(wrapper.text()).toContain('パイロット準備')
  })

  it('applies go class for Go recommendation', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ recommendation: 'Go' }) },
    })
    expect(wrapper.get('[data-testid="recommendation-badge"]').classes()).toContain('recommendation-go')
  })

  it('applies no-go class for No-Go recommendation', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ recommendation: 'No-Go' }) },
    })
    expect(wrapper.get('[data-testid="recommendation-badge"]').classes()).toContain('recommendation-no-go')
  })

  it('applies conditional class for 条件付きGo', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ recommendation: '条件付きGo' }) },
    })
    expect(wrapper.get('[data-testid="recommendation-badge"]').classes()).toContain('recommendation-conditional')
  })

  // --- B1: Card layout tests (TDD Red phase) ---

  it('renders a confidence gauge bar with correct width', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ agreement_score: 0.82 }) },
    })
    const gauge = wrapper.get('[data-testid="confidence-gauge"]')
    const fill = gauge.get('[data-testid="confidence-gauge-fill"]')
    expect(fill.attributes('style')).toContain('width: 82%')
  })

  it('renders confidence gauge at 0% when score is 0', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ agreement_score: 0 }) },
    })
    const fill = wrapper.get('[data-testid="confidence-gauge-fill"]')
    expect(fill.attributes('style')).toContain('width: 0%')
  })

  it('does not render confidence gauge when score is absent', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ agreement_score: undefined }) },
    })
    expect(wrapper.find('[data-testid="confidence-gauge"]').exists()).toBe(false)
  })

  it('renders detail sections as cards with data-testid', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.find('[data-testid="section-key-reasons"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-guardrails"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-deal-breakers"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-critical-unknowns"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-decision-scorecard"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="section-followup-prompts"]').exists()).toBe(true)
  })

  it('renders the hero card with summary and recommendation', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    const hero = wrapper.get('[data-testid="brief-hero-card"]')
    expect(hero.text()).toContain('Go')
    expect(hero.text()).toContain('市場参入を進めるが')
  })

  // --- Conversation Highlights tests ---

  const sampleHighlights = {
    summary: '価格仮説と市場規模について概ね合意が得られたが、参入タイミングで意見が分かれた。',
    source_phase: 'council' as const,
    consensus: [
      { point: '市場規模は十分に大きい', impact: 'Go判断の前提が成立' },
    ],
    conflicts: [
      { point: '参入タイミングが早すぎるか', status: 'unresolved', impact: '3ヶ月の遅延リスク' },
    ],
    turning_points: [
      { moment: 'パイロット成功率の共有後', why_it_changed: '懐疑派が条件付き賛成に転向' },
    ],
    key_quotes: [
      { speaker: 'CFO代理', quote: 'パイロットの転換率が40%を超えれば投資回収は見込める', decision_impact: '投資判断の閾値を定義' },
    ],
  }

  it('renders conversation highlights section when present', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ conversation_highlights: sampleHighlights }) },
    })
    const section = wrapper.find('[data-testid="section-conversation-highlights"]')
    expect(section.exists()).toBe(true)
    expect(section.text()).toContain('価格仮説と市場規模について概ね合意が得られたが、参入タイミングで意見が分かれた。')
  })

  it('hides conversation highlights section when absent', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief() },
    })
    expect(wrapper.find('[data-testid="section-conversation-highlights"]').exists()).toBe(false)
  })

  it('renders consensus items with green style', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ conversation_highlights: sampleHighlights }) },
    })
    const section = wrapper.get('[data-testid="section-conversation-highlights"]')
    expect(section.text()).toContain('市場規模は十分に大きい')
    expect(section.text()).toContain('Go判断の前提が成立')
    const consensusCard = section.find('.detail-card-consensus')
    expect(consensusCard.exists()).toBe(true)
  })

  it('renders conflict items with yellow style', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ conversation_highlights: sampleHighlights }) },
    })
    const section = wrapper.get('[data-testid="section-conversation-highlights"]')
    expect(section.text()).toContain('参入タイミングが早すぎるか')
    expect(section.text()).toContain('3ヶ月の遅延リスク')
    const conflictCard = section.find('.detail-card-conflict')
    expect(conflictCard.exists()).toBe(true)
  })

  it('renders turning points', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ conversation_highlights: sampleHighlights }) },
    })
    const section = wrapper.get('[data-testid="section-conversation-highlights"]')
    expect(section.text()).toContain('パイロット成功率の共有後')
    expect(section.text()).toContain('懐疑派が条件付き賛成に転向')
  })

  it('renders key quotes as blockquotes', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ conversation_highlights: sampleHighlights }) },
    })
    const section = wrapper.get('[data-testid="section-conversation-highlights"]')
    expect(section.text()).toContain('パイロットの転換率が40%を超えれば投資回収は見込める')
    expect(section.text()).toContain('CFO代理')
    expect(section.text()).toContain('投資判断の閾値を定義')
    expect(section.find('blockquote').exists()).toBe(true)
  })

  it('renders highlights between scorecard and followup sections', () => {
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ conversation_highlights: sampleHighlights }) },
    })
    const allSections = wrapper.findAll('[data-testid]')
    const testIds = allSections.map(el => el.attributes('data-testid'))
    const scorecardIdx = testIds.indexOf('section-decision-scorecard')
    const highlightsIdx = testIds.indexOf('section-conversation-highlights')
    const followupIdx = testIds.indexOf('section-followup-prompts')
    expect(scorecardIdx).toBeGreaterThanOrEqual(0)
    expect(highlightsIdx).toBeGreaterThanOrEqual(0)
    expect(followupIdx).toBeGreaterThanOrEqual(0)
    expect(highlightsIdx).toBeGreaterThan(scorecardIdx)
    expect(highlightsIdx).toBeLessThan(followupIdx)
  })

  it('handles highlights with empty arrays gracefully', () => {
    const sparseHighlights = {
      summary: 'サマリーのみ存在する。',
      source_phase: 'meeting' as const,
      consensus: [],
      conflicts: [],
      turning_points: [],
      key_quotes: [],
    }
    const wrapper = mount(DecisionBrief, {
      props: { brief: makeBrief({ conversation_highlights: sparseHighlights }) },
    })
    const section = wrapper.get('[data-testid="section-conversation-highlights"]')
    expect(section.text()).toContain('サマリーのみ存在する。')
    expect(section.find('.detail-card-consensus').exists()).toBe(false)
    expect(section.find('.detail-card-conflict').exists()).toBe(false)
    expect(section.find('blockquote').exists()).toBe(false)
  })
})
