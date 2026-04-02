import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CoalitionMap from '../CoalitionMap.vue'

function makeCoalitionMap(data: Record<string, unknown> = {}): Record<string, unknown> {
  return data
}

const SINGLE_DIMENSION: Record<string, unknown> = {
  age: {
    youth: { support: 0.72, oppose: 0.18 },
    elderly: { support: 0.35, oppose: 0.55 },
  },
}

const MULTI_DIMENSION: Record<string, unknown> = {
  age: {
    youth: { support: 0.72, oppose: 0.18 },
    elderly: { support: 0.35, oppose: 0.55 },
  },
  region: {
    urban: { support: 0.65, oppose: 0.25 },
    rural: { support: 0.4, oppose: 0.5 },
  },
}

describe('CoalitionMap', () => {
  it('renders the coalition map container', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    expect(wrapper.find('[data-testid="coalition-map"]').exists()).toBe(true)
  })

  it('renders coalition groups correctly', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    expect(rows.length).toBe(2)
    expect(wrapper.text()).toContain('age: youth')
    expect(wrapper.text()).toContain('age: elderly')
  })

  it('renders empty state when coalitionMap is empty', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap({}) },
    })
    expect(wrapper.findAll('[data-testid="coalition-row"]').length).toBe(0)
    expect(wrapper.text()).toContain('データなし')
  })

  it('renders empty state when coalitionMap is null-ish', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: null as unknown as Record<string, unknown> },
    })
    expect(wrapper.findAll('[data-testid="coalition-row"]').length).toBe(0)
    expect(wrapper.text()).toContain('データなし')
  })

  it('displays support percentage correctly', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    // youth support = 0.72 -> 72%
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    const youthRow = rows[0]
    expect(youthRow.find('.bar-pct-support').text()).toBe('72%')
  })

  it('displays oppose percentage correctly', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    // elderly oppose = 0.55 -> 55%
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    const elderlyRow = rows[1]
    expect(elderlyRow.find('.bar-pct-oppose').text()).toBe('55%')
  })

  it('sets support bar width style from percentage', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    const supportBar = rows[0].find('.bar-support')
    expect(supportBar.attributes('style')).toContain('width: 72%')
  })

  it('sets oppose bar width style from percentage', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    const opposeBar = rows[1].find('.bar-oppose')
    expect(opposeBar.attributes('style')).toContain('width: 55%')
  })

  it('sets title attributes on bars for accessibility', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    const supportBar = rows[0].find('.bar-support')
    const opposeBar = rows[0].find('.bar-oppose')
    expect(supportBar.attributes('title')).toBe('Support: 72%')
    expect(opposeBar.attributes('title')).toBe('Oppose: 18%')
  })

  it('handles multiple dimensions', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(MULTI_DIMENSION) },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    expect(rows.length).toBe(4)
    expect(wrapper.text()).toContain('age: youth')
    expect(wrapper.text()).toContain('age: elderly')
    expect(wrapper.text()).toContain('region: urban')
    expect(wrapper.text()).toContain('region: rural')
  })

  it('handles missing support/oppose values gracefully', () => {
    const wrapper = mount(CoalitionMap, {
      props: {
        coalitionMap: makeCoalitionMap({
          income: {
            high: { support: 0.6 },
            low: { oppose: 0.3 },
          },
        }),
      },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    expect(rows.length).toBe(2)
    // Missing oppose defaults to 0
    expect(rows[0].find('.bar-pct-support').text()).toBe('60%')
    expect(rows[0].find('.bar-pct-oppose').text()).toBe('0%')
    // Missing support defaults to 0
    expect(rows[1].find('.bar-pct-support').text()).toBe('0%')
    expect(rows[1].find('.bar-pct-oppose').text()).toBe('30%')
  })

  it('handles non-object segment values gracefully', () => {
    const wrapper = mount(CoalitionMap, {
      props: {
        coalitionMap: makeCoalitionMap({
          age: {
            youth: { support: 0.5, oppose: 0.3 },
            invalid: 'not an object',
            alsoInvalid: null,
          },
        }),
      },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    expect(rows.length).toBe(1)
    expect(wrapper.text()).toContain('age: youth')
  })

  it('handles non-object category values gracefully', () => {
    const wrapper = mount(CoalitionMap, {
      props: {
        coalitionMap: makeCoalitionMap({
          age: {
            youth: { support: 0.5, oppose: 0.3 },
          },
          broken: 'not an object',
          alsoNull: null,
        }),
      },
    })
    const rows = wrapper.findAll('[data-testid="coalition-row"]')
    expect(rows.length).toBe(1)
  })

  it('renders legend with Support and Oppose labels', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    expect(wrapper.find('.coalition-legend').exists()).toBe(true)
    expect(wrapper.text()).toContain('Support')
    expect(wrapper.text()).toContain('Oppose')
  })

  it('renders the title heading', () => {
    const wrapper = mount(CoalitionMap, {
      props: { coalitionMap: makeCoalitionMap(SINGLE_DIMENSION) },
    })
    expect(wrapper.find('.coalition-title').text()).toBe('Coalition Map')
  })

  it('rounds percentage to integer', () => {
    const wrapper = mount(CoalitionMap, {
      props: {
        coalitionMap: makeCoalitionMap({
          gender: {
            female: { support: 0.666, oppose: 0.123 },
          },
        }),
      },
    })
    const row = wrapper.get('[data-testid="coalition-row"]')
    // 0.666 * 100 = 66.6 -> toFixed(0) = "67"
    expect(row.find('.bar-pct-support').text()).toBe('67%')
    // 0.123 * 100 = 12.3 -> toFixed(0) = "12"
    expect(row.find('.bar-pct-oppose').text()).toBe('12%')
  })

  it('handles non-numeric support/oppose values gracefully', () => {
    const wrapper = mount(CoalitionMap, {
      props: {
        coalitionMap: makeCoalitionMap({
          edu: {
            college: { support: 'high', oppose: true },
          },
        }),
      },
    })
    const row = wrapper.get('[data-testid="coalition-row"]')
    // Non-numeric values default to 0
    expect(row.find('.bar-pct-support').text()).toBe('0%')
    expect(row.find('.bar-pct-oppose').text()).toBe('0%')
  })
})
