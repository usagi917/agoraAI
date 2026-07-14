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
    participant_name: '田中太郎',
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
        round_name: '深掘り',
      },
    ]

    const wrapper = mount(SocietyLiveFeed)
    const marker = wrapper.find('.feed-round')
    expect(marker.exists()).toBe(true)
    expect(marker.text()).toContain('Round 2')
    expect(marker.text()).toContain('深掘り')
  })

  it('filters dialogue and population voices in shifts-only mode while retaining shifts and rounds', async () => {
    const store = useSocietyGraphStore()
    store.feedEntries = [
      dialogueEntry(),
      { id: 'voice-1', kind: 'population_voice', round: 1, agent_id: 'citizen-1', comment: '市民意見', stance: '中立', occupation: '会社員', age_bracket: '40代' },
      { id: 'shift-1', kind: 'stance_shift', round: 1, participant: '田中太郎', from: '中立', to: '賛成' },
      { id: 'round-2', kind: 'round', round: 2 },
    ]
    const wrapper = mount(SocietyLiveFeed)

    await wrapper.find('.feed-filter-mode').setValue('shifts_only')

    expect(wrapper.find('.feed-dialogue').exists()).toBe(false)
    expect(wrapper.find('.feed-population-voice').exists()).toBe(false)
    expect(wrapper.find('.feed-stance-shift').exists()).toBe(true)
    expect(wrapper.find('.feed-round').exists()).toBe(true)
  })

  it('filters entries by related council agent while retaining round markers', async () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'agent-tanaka', agent_index: 1, name: '田中太郎', display_name: '田中太郎', occupation: '会社員', age: 40, region: '東京' },
      { id: 'agent-sato', agent_index: 2, name: '佐藤花子', display_name: '佐藤花子', occupation: '医師', age: 35, region: '大阪' },
    ])
    store.feedEntries = [
      dialogueEntry({ id: 'tanaka', participant_name: '田中太郎' }),
      dialogueEntry({ id: 'sato', participant_name: '佐藤花子' }),
      { id: 'shift-sato', kind: 'stance_shift', round: 1, participant: '佐藤花子', from: '中立', to: '賛成' },
      { id: 'round-2', kind: 'round', round: 2 },
      { id: 'voice-1', kind: 'population_voice', round: 2, agent_id: 'citizen-1', comment: '市民意見', stance: '中立' },
    ]
    const wrapper = mount(SocietyLiveFeed)

    await wrapper.find('.feed-filter-agent').setValue('agent-tanaka')

    expect(wrapper.findAll('.feed-dialogue')).toHaveLength(1)
    expect(wrapper.find('.feed-dialogue').text()).toContain('田中太郎')
    expect(wrapper.find('.feed-dialogue').text()).not.toContain('佐藤花子')
    expect(wrapper.find('.feed-round').exists()).toBe(true)
    expect(wrapper.find('.feed-population-voice').exists()).toBe(false)
  })

  it('emits resolved agent ids when speaker and addressee are clicked', async () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'agent-tanaka', agent_index: 1, name: '田中太郎', display_name: '田中太郎', occupation: '会社員', age: 40, region: '東京' },
      { id: 'agent-sato', agent_index: 2, name: '佐藤花子', display_name: '佐藤花子', occupation: '医師', age: 35, region: '大阪' },
    ])
    store.feedEntries = [dialogueEntry({ participant_name: '田中太郎', addressed_to: '佐藤花子' })]
    const wrapper = mount(SocietyLiveFeed)

    await wrapper.find('.feed-speaker').trigger('click')
    await wrapper.find('.feed-addressed').trigger('click')

    expect(wrapper.emitted('select-agent')).toEqual([['agent-tanaka']])
    expect(wrapper.emitted('highlight-edge')).toEqual([['agent-tanaka', 'agent-sato']])
  })

  it('emits the resolved agent id when a stance-shift participant is clicked', async () => {
    const store = useSocietyGraphStore()
    store.setSelectedAgents([
      { id: 'agent-tanaka', agent_index: 1, name: '田中太郎', display_name: '田中太郎', occupation: '会社員', age: 40, region: '東京' },
    ])
    store.feedEntries = [
      { id: 'shift-1', kind: 'stance_shift', round: 1, participant: '田中太郎', from: '中立', to: '賛成' },
    ]
    const wrapper = mount(SocietyLiveFeed)

    await wrapper.find('.shift-participant').trigger('click')

    expect(wrapper.emitted('select-agent')).toEqual([['agent-tanaka']])
  })

  it('renders and selects a visually distinct population voice', async () => {
    const store = useSocietyGraphStore()
    store.feedEntries = [{
      id: 'voice-citizen-9',
      kind: 'population_voice',
      round: 2,
      agent_id: 'citizen-9',
      agent_index: 9,
      comment: '生活費への影響が心配です。',
      stance: '反対',
      prev_stance: '中立',
      occupation: '会社員',
      age_bracket: '40代',
    }]
    const wrapper = mount(SocietyLiveFeed)
    const card = wrapper.find('.feed-population-voice')

    expect(card.exists()).toBe(true)
    expect(card.find('.feed-voice-badge').text()).toBe('市民の声')
    expect(card.text()).toContain('40代・会社員')
    expect(card.text()).toContain('中立')
    expect(card.text()).toContain('反対')
    expect(card.text()).toContain('生活費への影響が心配です。')

    await card.trigger('click')
    expect(wrapper.emitted('select-agent')).toEqual([['citizen-9']])
  })
})
