import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ForceGraph2D from '../ForceGraph2D.vue'

describe('ForceGraph2D', () => {
  it('renders SVG container with nodes and edges', async () => {
    const wrapper = mount(ForceGraph2D, {
      props: {
        nodes: [
          { id: 'n1', label: 'Node 1', type: 'organization', importance_score: 0.8, activity_score: 0 },
          { id: 'n2', label: 'Node 2', type: 'person', importance_score: 0.5, activity_score: 0 },
        ],
        edges: [
          { source: 'n1', target: 'n2', relation_type: 'trust', weight: 0.7, label: '' },
        ],
      },
    })
    await flushPromises()

    const svg = wrapper.find('svg')
    expect(svg.exists()).toBe(true)

    const circles = wrapper.findAll('circle')
    expect(circles.length).toBe(2)

    const lines = wrapper.findAll('line')
    expect(lines.length).toBe(1)
  })

  it('renders empty SVG when no data provided', async () => {
    const wrapper = mount(ForceGraph2D, {
      props: {
        nodes: [],
        edges: [],
      },
    })
    await flushPromises()

    const svg = wrapper.find('svg')
    expect(svg.exists()).toBe(true)
    expect(wrapper.findAll('circle').length).toBe(0)
    expect(wrapper.findAll('line').length).toBe(0)
  })

  it('shows node labels as text elements', async () => {
    const wrapper = mount(ForceGraph2D, {
      props: {
        nodes: [
          { id: 'n1', label: 'テスト', type: 'policy', importance_score: 0.6, activity_score: 0 },
        ],
        edges: [],
      },
    })
    await flushPromises()

    const texts = wrapper.findAll('text')
    expect(texts.some(t => t.text() === 'テスト')).toBe(true)
  })
})
