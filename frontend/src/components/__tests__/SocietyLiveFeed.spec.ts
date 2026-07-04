import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import SocietyLiveFeed from '../SocietyLiveFeed.vue'
import { useSocietyGraphStore, type FeedEntry } from '../../stores/societyGraphStore'

let idSeq = 0

function dialogueEntry(overrides: Partial<FeedEntry> = {}): FeedEntry {
  return {
    id: `dialogue-${idSeq++}`,
    kind: 'dialogue',
    round: 1,
    receivedAt: Date.now(),
    participant_name: '田中太郎',
    role: 'expert',
    position: '中立',
    argument: '発言内容です。',
    ...overrides,
  }
}

describe('SocietyLiveFeed', () => {
  beforeEach(() => {
    idSeq = 0
    setActivePinia(createPinia())
  })

  it('shows a waiting state when the feed is empty', () => {
    const wrapper = mount(SocietyLiveFeed)
    expect(wrapper.find('.feed-empty').exists()).toBe(true)
    expect(wrapper.findAll('.feed-item').length).toBe(0)
  })

  it('renders a dialogue entry with speaker, body, addressee and stance class', () => {
    const store = useSocietyGraphStore()
    store.feedEntries = [
      dialogueEntry({
        participant_name: '佐藤花子',
        argument: 'この政策に賛成です',
        position: '賛成',
        addressed_to: '田中太郎',
      }),
    ]

    const wrapper = mount(SocietyLiveFeed)
    const card = wrapper.find('.feed-dialogue')
    expect(card.exists()).toBe(true)
    expect(card.find('.feed-speaker').text()).toBe('佐藤花子')
    expect(card.find('.feed-body').text()).toContain('この政策に賛成です')
    expect(card.find('.feed-addressed').text()).toContain('田中太郎')
    expect(card.classes()).toContain('stance-agree')
  })

  it('truncates long dialogue bodies to ~150 chars', () => {
    const store = useSocietyGraphStore()
    const long = 'あ'.repeat(300)
    store.feedEntries = [dialogueEntry({ argument: long })]

    const wrapper = mount(SocietyLiveFeed)
    const body = wrapper.find('.feed-body').text()
    expect(body.length).toBeLessThan(long.length)
    expect(body).toContain('…')
  })

  it('alternates entries left and right', () => {
    const store = useSocietyGraphStore()
    store.feedEntries = [
      dialogueEntry({ argument: 'A' }),
      dialogueEntry({ argument: 'B' }),
      dialogueEntry({ argument: 'C' }),
    ]

    const wrapper = mount(SocietyLiveFeed)
    const items = wrapper.findAll('.feed-item')
    expect(items.length).toBe(3)
    expect(items[0].classes()).toContain('left')
    expect(items[1].classes()).toContain('right')
    expect(items[2].classes()).toContain('left')
  })

  it('renders a stance_shift entry with from/to chips', () => {
    const store = useSocietyGraphStore()
    store.feedEntries = [
      {
        id: 'shift-1',
        kind: 'stance_shift',
        round: 2,
        receivedAt: Date.now(),
        participant: '田中太郎',
        from: '中立',
        to: '賛成',
        reason: '議論の結果、納得した',
      },
    ]

    const wrapper = mount(SocietyLiveFeed)
    const card = wrapper.find('.feed-stance-shift')
    expect(card.exists()).toBe(true)
    expect(card.find('.shift-from').text()).toContain('中立')
    expect(card.find('.shift-to').text()).toContain('賛成')
    expect(card.text()).toContain('議論の結果、納得した')
  })

  it('renders only the last 150 entries to bound the DOM', () => {
    const store = useSocietyGraphStore()
    store.feedEntries = Array.from({ length: 200 }, (_, i) =>
      dialogueEntry({ id: `d-${i}`, argument: `msg-${i}` }),
    )

    const wrapper = mount(SocietyLiveFeed)
    const items = wrapper.findAll('.feed-item')
    expect(items.length).toBe(150)
    // tail slice: newest is rendered, entries before the 150-window are not
    expect(wrapper.text()).toContain('msg-199')
    expect(wrapper.text()).not.toContain('msg-49')
  })

  it('renders a round marker entry', () => {
    const store = useSocietyGraphStore()
    store.feedEntries = [
      {
        id: 'round-2',
        kind: 'round',
        round: 2,
        receivedAt: Date.now(),
        round_name: '深掘り',
      },
    ]

    const wrapper = mount(SocietyLiveFeed)
    const marker = wrapper.find('.feed-round')
    expect(marker.exists()).toBe(true)
    expect(marker.text()).toContain('Round 2')
    expect(marker.text()).toContain('深掘り')
  })
})
