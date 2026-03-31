import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DigitalWorkspaceBackground from '../DigitalWorkspaceBackground.vue'

describe('DigitalWorkspaceBackground', () => {
  it('renders all three layers', () => {
    const wrapper = mount(DigitalWorkspaceBackground)

    expect(wrapper.find('[data-testid="data-rain"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scan-line"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="grid-pulse"]').exists()).toBe(true)
  })

  it('renders 20 data rain columns', () => {
    const wrapper = mount(DigitalWorkspaceBackground)
    const columns = wrapper.findAll('.rain-column')

    expect(columns).toHaveLength(20)
  })

  it('applies correct CSS class based on mode prop', () => {
    const wrapper = mount(DigitalWorkspaceBackground, {
      props: { mode: 'society' },
    })
    const container = wrapper.find('[data-testid="digital-workspace-bg"]')

    expect(container.classes()).toContain('mode-society')
  })

  it('renders without errors when no mode is provided', () => {
    const wrapper = mount(DigitalWorkspaceBackground)
    const container = wrapper.find('[data-testid="digital-workspace-bg"]')

    expect(container.exists()).toBe(true)
    expect(container.classes()).toContain('mode-idle')
  })
})
