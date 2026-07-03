import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ConditionStrip from '../ConditionStrip.vue'
import DistributionCompare from '../DistributionCompare.vue'
import OpinionBubbles from '../OpinionBubbles.vue'
import ValidationVerdictCard from '../ValidationVerdictCard.vue'

describe('validation components', () => {
  it('renders verdict metrics', () => {
    const wrapper = mount(ValidationVerdictCard, {
      props: { verdict: 'hit', jsd: 0.01, emd: 0.02, brier: 0.03 },
    })

    expect(wrapper.text()).toContain('的中')
    expect(wrapper.text()).toContain('0.010')
    expect(wrapper.classes()).toContain('verdict-hit')
  })

  it('renders distribution totals and stance rows', () => {
    const dist = {
      賛成: 0.2,
      条件付き賛成: 0.2,
      中立: 0.2,
      条件付き反対: 0.2,
      反対: 0.2,
    }
    const wrapper = mount(DistributionCompare, {
      props: { predicted: dist, actual: dist },
    })

    expect(wrapper.text()).toContain('予測 100% / 実測 100%')
    expect(wrapper.text()).toContain('条件付き反対')
  })

  it('sorts condition cards by jsd', () => {
    const wrapper = mount(ConditionStrip, {
      props: {
        evaluations: [
          { survey_id: 'b', theme: 'B', question: '', source: '', predicted: {}, actual: {}, jsd: 0.3, emd: 0.2, brier: 0.1, ece: null, verdict: 'miss' },
          { survey_id: 'a', theme: 'A', question: '', source: '', predicted: {}, actual: {}, jsd: 0.1, emd: 0.1, brier: 0.1, ece: null, verdict: 'hit' },
        ],
      },
    })

    const labels = wrapper.findAll('.condition-label').map((node) => node.text())
    expect(labels).toEqual(['A', 'B'])
  })

  it('does not render opinion bubbles without reasons', () => {
    const wrapper = mount(OpinionBubbles, { props: { opinions: [] } })

    expect(wrapper.find('.opinion-bubbles').exists()).toBe(false)
  })

  it('pins an opinion bubble on click', async () => {
    vi.useFakeTimers()
    const wrapper = mount(OpinionBubbles, {
      props: {
        opinions: [
          { agent_id: '1', stance: '賛成', reason: 'a' },
          { agent_id: '2', stance: '反対', reason: 'b' },
          { agent_id: '3', stance: '中立', reason: 'c' },
          { agent_id: '4', stance: '賛成', reason: 'd' },
        ],
      },
    })

    await wrapper.findAll('.opinion-bubble')[1].trigger('click')

    expect(wrapper.findAll('.opinion-bubble')).toHaveLength(1)
    expect(wrapper.text()).toContain('b')
    vi.useRealTimers()
  })
})
