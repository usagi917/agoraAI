import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSocietyGraphStore } from '../../stores/societyGraphStore'
import GraphDevPage from '../GraphDevPage.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
}))

describe('GraphDevPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('cancels its async graph harness on unmount', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useSocietyGraphStore()
    const updateActivationProgress = vi.spyOn(store, 'updateActivationProgress')
    const hydrateWithSocialGraph = vi.spyOn(store, 'hydrateWithSocialGraph')

    const wrapper = mount(GraphDevPage, {
      global: {
        plugins: [pinia],
        stubs: {
          LiveSocietyGraph: { template: '<div />' },
        },
      },
    })

    const callsAtUnmount = updateActivationProgress.mock.calls.length
    wrapper.unmount()

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(updateActivationProgress).toHaveBeenCalledTimes(callsAtUnmount)
    expect(hydrateWithSocialGraph).not.toHaveBeenCalled()
  })
})
