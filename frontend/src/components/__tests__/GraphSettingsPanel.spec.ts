import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import GraphSettingsPanel from '../GraphSettingsPanel.vue'
import { DEFAULT_PHYSICS } from '../forceGraphHelpers'

describe('GraphSettingsPanel', () => {
  it('renders sliders for the four physics parameters', () => {
    const wrapper = mount(GraphSettingsPanel, {
      props: { physics: { ...DEFAULT_PHYSICS } },
    })
    const sliders = wrapper.findAll('input[type="range"]')
    expect(sliders).toHaveLength(4)
  })

  it('emits update:physics when a slider changes', async () => {
    const wrapper = mount(GraphSettingsPanel, {
      props: { physics: { ...DEFAULT_PHYSICS } },
    })
    const charge = wrapper.find('[data-testid="physics-charge"]')
    await charge.setValue('-500')

    const emitted = wrapper.emitted('update:physics')
    expect(emitted).toBeTruthy()
    const payload = emitted!.at(-1)![0] as { chargeStrength: number }
    expect(payload.chargeStrength).toBe(-500)
    // 他のパラメータは保持される
    expect(payload).toMatchObject({
      linkDistance: DEFAULT_PHYSICS.linkDistance,
      centerStrength: DEFAULT_PHYSICS.centerStrength,
      collidePadding: DEFAULT_PHYSICS.collidePadding,
    })
  })

  it('resets to defaults when reset button is clicked', async () => {
    const wrapper = mount(GraphSettingsPanel, {
      props: { physics: { ...DEFAULT_PHYSICS, chargeStrength: -500 } },
    })
    await wrapper.find('[data-testid="physics-reset"]').trigger('click')

    const emitted = wrapper.emitted('update:physics')
    expect(emitted).toBeTruthy()
    expect(emitted!.at(-1)![0]).toEqual(DEFAULT_PHYSICS)
  })
})
