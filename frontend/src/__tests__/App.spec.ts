import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import App from '../App.vue'

describe('App navigation', () => {
  it('describes each destination in user-facing language', () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          RouterView: { template: '<main />' },
        },
      },
    })

    const navigation = wrapper.get('nav[aria-label="分析メニュー"]')
    expect(navigation.text()).toContain('新規分析')
    expect(navigation.text()).toContain('条件を比較')
    expect(navigation.text()).toContain('対象者を管理')
    expect(navigation.text()).not.toContain('精度を検証')
  })
})
