import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ComparisonBrief from '../ComparisonBrief.vue'
import type { ComparisonResult } from '../../stores/scenarioPairStore'

function makeComparison(overrides: Partial<ComparisonResult> = {}): ComparisonResult {
  return {
    scenario_pair_id: 'pair-1',
    baseline_brief: {
      recommendation: 'Go',
      agreement_score: 0.82,
      decision_summary: 'Baseline summary text',
    },
    intervention_brief: {
      recommendation: 'No-Go',
      agreement_score: 0.45,
      decision_summary: 'Intervention summary text',
    },
    delta: {
      support_change: -0.27,
      new_concerns: ['Cost increase for low-income households'],
      coalition_shifts: [{ group: 'youth', from: 'support', to: 'oppose' }],
      key_differences: ['Urban support dropped by 30%'],
    },
    opinion_shifts_top5: [],
    coalition_map: {},
    ...overrides,
  }
}

describe('ComparisonBrief', () => {
  it('renders the comparison brief container', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    expect(wrapper.find('[data-testid="comparison-brief"]').exists()).toBe(true)
  })

  it('renders baseline and intervention panels on desktop', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    expect(wrapper.find('[data-testid="baseline-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="intervention-panel"]').exists()).toBe(true)
  })

  it('renders baseline brief recommendation text', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    const baselinePanel = wrapper.get('[data-testid="baseline-panel"]')
    expect(baselinePanel.text()).toContain('Go')
  })

  it('renders intervention brief recommendation text', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    const interventionPanel = wrapper.get('[data-testid="intervention-panel"]')
    expect(interventionPanel.text()).toContain('No-Go')
  })

  it('renders delta summary section', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    expect(wrapper.find('[data-testid="delta-summary"]').exists()).toBe(true)
  })

  it('shows support change with correct sign', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    const delta = wrapper.get('[data-testid="delta-summary"]')
    // -27.0%
    expect(delta.text()).toContain('-27.0%')
  })

  it('shows positive support change with + prefix', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison({ delta: { support_change: 0.15, new_concerns: [], coalition_shifts: [], key_differences: [] } }) },
    })
    const delta = wrapper.get('[data-testid="delta-summary"]')
    expect(delta.text()).toContain('+15.0%')
  })

  it('renders new concerns list', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    expect(wrapper.text()).toContain('Cost increase for low-income households')
  })

  it('renders key differences list', () => {
    const wrapper = mount(ComparisonBrief, {
      props: { comparison: makeComparison() },
    })
    expect(wrapper.text()).toContain('Urban support dropped by 30%')
  })

  it('shows empty state when baseline brief is null', () => {
    const wrapper = mount(ComparisonBrief, {
      props: {
        comparison: makeComparison({
          baseline_brief: null as unknown as Record<string, unknown>,
        }),
      },
    })
    expect(wrapper.text()).toContain('介入なし')
  })
})
