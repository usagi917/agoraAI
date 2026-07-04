import { describe, expect, it } from 'vitest'

import {
  derivePulseUpdate,
  derivePulses,
  pulseKey,
  type PulseAgentRef,
  type PulseArgument,
  type PulseCursor,
} from '../liveGraphPulses'

const agents: PulseAgentRef[] = [
  { id: 'agent-1', agentIndex: 1, displayName: '田中', label: '会社員, 35歳' },
  { id: 'agent-2', agentIndex: 2, displayName: '佐藤', label: '医師, 42歳' },
  { id: 'agent-3', agentIndex: 3, displayName: '鈴木', label: '教員, 50歳' },
]

const arg = (overrides: Partial<PulseArgument> = {}): PulseArgument => ({
  participant_index: 1,
  participant_name: '田中',
  argument: 'text',
  ...overrides,
})

describe('derivePulses', () => {
  it('derives a pulse from an explicit addressed index', () => {
    const pulses = derivePulses(
      [arg({ participant_index: 1, addressed_to_participant_index: 2 })],
      1,
      agents,
      new Set(),
    )
    expect(pulses).toHaveLength(1)
    expect(pulses[0]).toMatchObject({ sourceId: 'agent-1', targetId: 'agent-2' })
  })

  it('resolves the target by name when no addressed index is given', () => {
    const pulses = derivePulses(
      [arg({ participant_index: 1, addressed_to: '佐藤さんに質問です' })],
      1,
      agents,
      new Set(),
    )
    expect(pulses).toHaveLength(1)
    expect(pulses[0].targetId).toBe('agent-2')
  })

  it('skips speeches with no resolvable addressee (speaker-only)', () => {
    const pulses = derivePulses(
      [arg({ participant_index: 1, addressed_to: undefined, addressed_to_participant_index: null })],
      1,
      agents,
      new Set(),
    )
    expect(pulses).toEqual([])
  })

  it('does not re-fire arguments whose key is already processed', () => {
    const processed = new Set<string>()
    const first = derivePulses(
      [arg({ participant_index: 1, addressed_to_participant_index: 2 })],
      1,
      agents,
      processed,
    )
    expect(first).toHaveLength(1)
    first.forEach((p) => processed.add(p.key))

    const second = derivePulses(
      [arg({ participant_index: 1, addressed_to_participant_index: 2 })],
      1,
      agents,
      processed,
    )
    expect(second).toEqual([])
  })

  it('treats the same exchange in a new round as a fresh pulse', () => {
    const processed = new Set<string>()
    const exchange = arg({ participant_index: 1, addressed_to_participant_index: 2 })
    derivePulses([exchange], 1, agents, processed).forEach((p) => processed.add(p.key))

    const round2 = derivePulses([exchange], 2, agents, processed)
    expect(round2).toHaveLength(1)
    expect(round2[0].key).not.toBe(pulseKey(1, exchange))
  })

  it('skips arguments whose speaker or addressee cannot be resolved to a node', () => {
    const unknownSpeaker = derivePulses(
      [arg({ participant_index: 99, addressed_to_participant_index: 2 })],
      1,
      agents,
      new Set(),
    )
    expect(unknownSpeaker).toEqual([])

    const unknownTarget = derivePulses(
      [arg({ participant_index: 1, addressed_to: '知らない人', addressed_to_participant_index: 404 })],
      1,
      agents,
      new Set(),
    )
    expect(unknownTarget).toEqual([])
  })

  it('ignores self-addressed speeches', () => {
    const pulses = derivePulses(
      [arg({ participant_index: 1, addressed_to_participant_index: 1 })],
      1,
      agents,
      new Set(),
    )
    expect(pulses).toEqual([])
  })
})

describe('derivePulseUpdate', () => {
  const start: PulseCursor = { round: -1, count: 0 }

  it('only scans the newly appended tail on each successive call', () => {
    const a1 = arg({ participant_index: 1, addressed_to_participant_index: 2, argument: 'one' })
    const a2 = arg({ participant_index: 2, addressed_to_participant_index: 1, argument: 'two' })

    const first = derivePulseUpdate([a1], 1, agents, start)
    expect(first.pulses).toHaveLength(1)
    expect(first.pulses[0]).toMatchObject({ sourceId: 'agent-1', targetId: 'agent-2' })

    // Full array passed again, but only the appended a2 is scanned (not a1 again).
    const second = derivePulseUpdate([a1, a2], 1, agents, first.cursor)
    expect(second.pulses).toHaveLength(1)
    expect(second.pulses[0]).toMatchObject({ sourceId: 'agent-2', targetId: 'agent-1' })

    // No new appends → no rescanning, no pulses.
    const third = derivePulseUpdate([a1, a2], 1, agents, second.cursor)
    expect(third.pulses).toEqual([])
  })

  it('rewinds the cursor when the round advances (array reset)', () => {
    const a1 = arg({ participant_index: 1, addressed_to_participant_index: 2 })
    const round1 = derivePulseUpdate([a1], 1, agents, start)
    expect(round1.pulses).toHaveLength(1)

    // Round 2 resets currentArguments to a fresh, shorter array.
    const round2 = derivePulseUpdate([a1], 2, agents, round1.cursor)
    expect(round2.pulses).toHaveLength(1)
    expect(round2.cursor).toEqual({ round: 2, count: 1 })
  })

  it('rewinds when the array shrinks within the same round (clearSpeaking)', () => {
    const a1 = arg({ participant_index: 1, addressed_to_participant_index: 2 })
    const a2 = arg({ participant_index: 2, addressed_to_participant_index: 1, argument: 'two' })
    const seeded = derivePulseUpdate([a1, a2], 1, agents, start)
    expect(seeded.cursor).toEqual({ round: 1, count: 2 })

    const cleared = derivePulseUpdate([], 1, agents, seeded.cursor)
    expect(cleared.pulses).toEqual([])
    expect(cleared.cursor).toEqual({ round: 1, count: 0 })
  })
})
