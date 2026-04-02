import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OpinionShiftTable from '../OpinionShiftTable.vue'
import type { OpinionShift } from '../OpinionShiftTable.vue'

const MOCK_SHIFTS: OpinionShift[] = [
  {
    agent_name: 'Tanaka Yuki',
    before: 'support',
    after: 'oppose',
    reasoning: 'Changed stance due to rising implementation costs that would disproportionately affect small businesses in rural areas, outweighing the projected benefits.',
  },
  {
    agent_name: 'Suzuki Aoi',
    before: 'neutral',
    after: 'support',
    reasoning: 'Short reason',
  },
  {
    agent_name: 'Sato Kenji',
    before: 'oppose',
    after: 'neutral',
    reasoning: 'Convinced by new evidence',
  },
]

describe('OpinionShiftTable', () => {
  it('renders the table container', () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: MOCK_SHIFTS },
    })
    expect(wrapper.find('[data-testid="opinion-shift-table"]').exists()).toBe(true)
  })

  it('renders correct number of rows', () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: MOCK_SHIFTS },
    })
    const rows = wrapper.findAll('[data-testid="shift-row"]')
    expect(rows.length).toBe(3)
  })

  it('renders agent names', () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: MOCK_SHIFTS },
    })
    expect(wrapper.text()).toContain('Tanaka Yuki')
    expect(wrapper.text()).toContain('Suzuki Aoi')
    expect(wrapper.text()).toContain('Sato Kenji')
  })

  it('renders before and after stances', () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: MOCK_SHIFTS },
    })
    expect(wrapper.text()).toContain('support')
    expect(wrapper.text()).toContain('oppose')
    expect(wrapper.text()).toContain('neutral')
  })

  it('shows expand button for long reasoning text', () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: MOCK_SHIFTS },
    })
    const expandBtns = wrapper.findAll('[data-testid="expand-btn"]')
    // Only the first shift has reasoning > 80 chars
    expect(expandBtns.length).toBe(1)
  })

  it('toggles expanded reasoning on click', async () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: MOCK_SHIFTS },
    })
    const expandBtn = wrapper.get('[data-testid="expand-btn"]')
    expect(expandBtn.text()).toBe('more')

    await expandBtn.trigger('click')
    expect(expandBtn.text()).toBe('less')

    await expandBtn.trigger('click')
    expect(expandBtn.text()).toBe('more')
  })

  it('shows empty state when no shifts provided', () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: [] },
    })
    expect(wrapper.text()).toContain('データなし')
    expect(wrapper.findAll('[data-testid="shift-row"]').length).toBe(0)
  })

  it('renders table headers', () => {
    const wrapper = mount(OpinionShiftTable, {
      props: { shifts: MOCK_SHIFTS },
    })
    expect(wrapper.text()).toContain('Agent')
    expect(wrapper.text()).toContain('Before')
    expect(wrapper.text()).toContain('After')
    expect(wrapper.text()).toContain('Reasoning')
  })
})
