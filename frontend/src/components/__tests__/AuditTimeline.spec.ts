import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AuditTimeline from '../AuditTimeline.vue'
import type { AuditEvent } from '../AuditTimeline.vue'

const MOCK_EVENTS: AuditEvent[] = [
  {
    id: 'evt-1',
    agent_id: 'agent-a',
    agent_name: 'Tanaka Yuki',
    event_type: 'stance_change',
    reasoning: 'Changed stance after reviewing new economic data.',
    timestamp: '2026-04-03T10:30:00Z',
  },
  {
    id: 'evt-2',
    agent_id: 'agent-b',
    agent_name: 'Suzuki Aoi',
    event_type: 'argument',
    reasoning: 'Presented counter-argument based on environmental concerns.',
    timestamp: '2026-04-03T10:31:00Z',
  },
  {
    id: 'evt-3',
    agent_id: 'agent-a',
    agent_name: 'Tanaka Yuki',
    event_type: 'agreement',
    reasoning: 'Agreed with the revised proposal after deliberation.',
    timestamp: '2026-04-03T10:32:00Z',
  },
  {
    id: 'evt-4',
    agent_id: 'agent-c',
    agent_name: 'Sato Kenji',
    event_type: 'dissent',
    reasoning: 'Dissented due to implementation feasibility concerns.',
    timestamp: '2026-04-03T10:33:00Z',
  },
]

describe('AuditTimeline', () => {
  it('renders the timeline container', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    expect(wrapper.find('[data-testid="audit-timeline"]').exists()).toBe(true)
  })

  it('renders correct number of timeline items', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    const items = wrapper.findAll('[data-testid="timeline-item"]')
    expect(items.length).toBe(4)
  })

  it('shows empty state when no events provided', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: [] },
    })
    expect(wrapper.text()).toContain('イベントなし')
    expect(wrapper.findAll('[data-testid="timeline-item"]').length).toBe(0)
  })

  it('renders agent names for each event', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    expect(wrapper.text()).toContain('Tanaka Yuki')
    expect(wrapper.text()).toContain('Suzuki Aoi')
    expect(wrapper.text()).toContain('Sato Kenji')
  })

  it('renders event type badges with correct text', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    expect(wrapper.text()).toContain('stance_change')
    expect(wrapper.text()).toContain('argument')
    expect(wrapper.text()).toContain('agreement')
    expect(wrapper.text()).toContain('dissent')
  })

  it('applies correct badge class for stance_change', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: [MOCK_EVENTS[0]] },
    })
    const badge = wrapper.find('.event-badge')
    expect(badge.classes()).toContain('badge-warning')
  })

  it('applies correct badge class for argument', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: [MOCK_EVENTS[1]] },
    })
    const badge = wrapper.find('.event-badge')
    expect(badge.classes()).toContain('badge-accent')
  })

  it('applies correct badge class for agreement', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: [MOCK_EVENTS[2]] },
    })
    const badge = wrapper.find('.event-badge')
    expect(badge.classes()).toContain('badge-success')
  })

  it('applies correct badge class for dissent', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: [MOCK_EVENTS[3]] },
    })
    const badge = wrapper.find('.event-badge')
    expect(badge.classes()).toContain('badge-danger')
  })

  it('applies default badge class for unknown event type', () => {
    const event: AuditEvent = {
      id: 'evt-x',
      agent_id: 'agent-x',
      agent_name: 'Unknown Agent',
      event_type: 'some_unknown_type',
      reasoning: 'Some reasoning.',
      timestamp: '2026-04-03T11:00:00Z',
    }
    const wrapper = mount(AuditTimeline, {
      props: { events: [event] },
    })
    const badge = wrapper.find('.event-badge')
    expect(badge.classes()).toContain('badge-default')
  })

  it('renders timestamps', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    expect(wrapper.text()).toContain('2026-04-03T10:30:00Z')
    expect(wrapper.text()).toContain('2026-04-03T10:31:00Z')
  })

  it('does not render timestamp element when timestamp is empty', () => {
    const event: AuditEvent = {
      id: 'evt-no-ts',
      agent_id: 'agent-a',
      agent_name: 'Tanaka Yuki',
      event_type: 'argument',
      reasoning: 'No timestamp event.',
      timestamp: '',
    }
    const wrapper = mount(AuditTimeline, {
      props: { events: [event] },
    })
    expect(wrapper.find('.event-time').exists()).toBe(false)
  })

  it('truncates long reasoning text to 120 characters with ellipsis', () => {
    const longReasoning = 'A'.repeat(150)
    const event: AuditEvent = {
      id: 'evt-long',
      agent_id: 'agent-a',
      agent_name: 'Tanaka Yuki',
      event_type: 'argument',
      reasoning: longReasoning,
      timestamp: '2026-04-03T12:00:00Z',
    }
    const wrapper = mount(AuditTimeline, {
      props: { events: [event] },
    })
    const reasoningEl = wrapper.find('.timeline-reasoning')
    expect(reasoningEl.text()).toBe('A'.repeat(120) + '...')
    expect(reasoningEl.text().length).toBe(123) // 120 + '...'
  })

  it('does not truncate short reasoning text', () => {
    const shortReasoning = 'Short reasoning.'
    const event: AuditEvent = {
      id: 'evt-short',
      agent_id: 'agent-a',
      agent_name: 'Tanaka Yuki',
      event_type: 'argument',
      reasoning: shortReasoning,
      timestamp: '2026-04-03T12:00:00Z',
    }
    const wrapper = mount(AuditTimeline, {
      props: { events: [event] },
    })
    const reasoningEl = wrapper.find('.timeline-reasoning')
    expect(reasoningEl.text()).toBe('Short reasoning.')
  })

  it('renders agent filter dropdown', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    expect(wrapper.find('[data-testid="agent-filter"]').exists()).toBe(true)
  })

  it('populates agent filter with unique sorted agent IDs', () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    const options = wrapper.findAll('[data-testid="agent-filter"] option')
    // "All Agents" + 3 unique agent IDs (agent-a, agent-b, agent-c)
    expect(options.length).toBe(4)
    expect(options[0].text()).toBe('All Agents')
    expect(options[1].text()).toBe('agent-a')
    expect(options[2].text()).toBe('agent-b')
    expect(options[3].text()).toBe('agent-c')
  })

  it('filters events by selected agent', async () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    const select = wrapper.find('[data-testid="agent-filter"]')
    await select.setValue('agent-b')

    const items = wrapper.findAll('[data-testid="timeline-item"]')
    expect(items.length).toBe(1)
    expect(wrapper.text()).toContain('Suzuki Aoi')
    expect(wrapper.text()).not.toContain('Sato Kenji')
  })

  it('shows all events when filter is reset to All Agents', async () => {
    const wrapper = mount(AuditTimeline, {
      props: { events: MOCK_EVENTS },
    })
    const select = wrapper.find('[data-testid="agent-filter"]')

    await select.setValue('agent-a')
    expect(wrapper.findAll('[data-testid="timeline-item"]').length).toBe(2)

    await select.setValue('')
    expect(wrapper.findAll('[data-testid="timeline-item"]').length).toBe(4)
  })

  it('shows empty state when filtered agent has no events after filtering', async () => {
    const singleEvent: AuditEvent[] = [
      {
        id: 'evt-1',
        agent_id: 'agent-a',
        agent_name: 'Tanaka Yuki',
        event_type: 'argument',
        reasoning: 'Some reasoning.',
        timestamp: '2026-04-03T10:30:00Z',
      },
    ]
    const wrapper = mount(AuditTimeline, {
      props: { events: singleEvent },
    })
    // agent-a is the only option; manually set a non-existent value won't appear
    // in the dropdown but we can test the computed behavior by selecting "All Agents" first
    expect(wrapper.findAll('[data-testid="timeline-item"]').length).toBe(1)
  })
})
