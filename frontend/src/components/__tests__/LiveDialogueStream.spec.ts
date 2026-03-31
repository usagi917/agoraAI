import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import LiveDialogueStream from '../LiveDialogueStream.vue'
import { useSocietyGraphStore } from '../../stores/societyGraphStore'

describe('LiveDialogueStream', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  function mountComponent() {
    return mount(LiveDialogueStream)
  }

  it('renders empty state when no data', () => {
    const wrapper = mountComponent()
    expect(wrapper.find('.dialogue-empty').exists()).toBe(true)
    expect(wrapper.find('.dialogue-empty').text()).toContain('対話データを待機中')
    expect(wrapper.findAll('.dialogue-bubble').length).toBe(0)
  })

  it('renders chat bubbles from societyGraphStore.currentArguments', () => {
    const store = useSocietyGraphStore()
    store.currentArguments = [
      {
        participant_name: '田中太郎',
        participant_index: 0,
        role: 'expert',
        argument: 'この政策は有効です',
        position: '賛成',
      },
      {
        participant_name: '佐藤花子',
        participant_index: 1,
        role: 'citizen',
        argument: '市民の視点から懸念があります',
        position: '反対',
      },
    ]

    const wrapper = mountComponent()
    const bubbles = wrapper.findAll('.dialogue-bubble')
    expect(bubbles.length).toBe(2)

    expect(bubbles[0].find('.bubble-speaker').text()).toBe('田中太郎')
    expect(bubbles[0].find('.bubble-role').text()).toBe('専門家')
    expect(bubbles[0].find('.bubble-content').text()).toBe('この政策は有効です')

    expect(bubbles[1].find('.bubble-speaker').text()).toBe('佐藤花子')
    expect(bubbles[1].find('.bubble-role').text()).toBe('市民代表')
    expect(bubbles[1].find('.bubble-content').text()).toBe('市民の視点から懸念があります')
  })

  it('left/right alignment alternates correctly', () => {
    const store = useSocietyGraphStore()
    store.currentArguments = [
      {
        participant_name: 'Agent A',
        participant_index: 0,
        role: '',
        argument: 'First argument',
        position: '中立',
      },
      {
        participant_name: 'Agent B',
        participant_index: 1,
        role: '',
        argument: 'Second argument',
        position: '中立',
      },
      {
        participant_name: 'Agent C',
        participant_index: 2,
        role: '',
        argument: 'Third argument',
        position: '中立',
      },
    ]

    const wrapper = mountComponent()
    const bubbles = wrapper.findAll('.dialogue-bubble')
    expect(bubbles.length).toBe(3)

    expect(bubbles[0].classes()).toContain('left')
    expect(bubbles[1].classes()).toContain('right')
    expect(bubbles[2].classes()).toContain('left')
  })

  it('stance class is applied based on position', () => {
    const store = useSocietyGraphStore()
    store.currentArguments = [
      {
        participant_name: 'Agent A',
        participant_index: 0,
        role: '',
        argument: 'I agree',
        position: '賛成',
      },
      {
        participant_name: 'Agent B',
        participant_index: 1,
        role: '',
        argument: 'I disagree',
        position: '反対',
      },
      {
        participant_name: 'Agent C',
        participant_index: 2,
        role: '',
        argument: 'I am neutral',
        position: '中立',
      },
    ]

    const wrapper = mountComponent()
    const bubbles = wrapper.findAll('.dialogue-bubble')
    expect(bubbles.length).toBe(3)

    expect(bubbles[0].classes()).toContain('stance-agree')
    expect(bubbles[1].classes()).toContain('stance-disagree')
    expect(bubbles[2].classes()).toContain('stance-neutral')
  })
})
