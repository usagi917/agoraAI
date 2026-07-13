import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { GraphActivityEvent } from '../../api/client'
import { mergeGraphActivityEvents } from '../../services/graphActivitySync'
import { useSocialGraphActivityStore } from '../socialGraphActivityStore'

function event(id: number, kind: GraphActivityEvent['kind'] = 'dialogue'): GraphActivityEvent {
  return {
    id,
    simulation_id: 'sim-1',
    occurred_at: `2026-07-13T00:00:0${id}Z`,
    phase: 'meeting',
    round: 2,
    kind,
    source_id: 'agent-1',
    target_id: 'agent-2',
    edge_id: 'edge-1',
    payload: {},
  }
}

describe('socialGraphActivityStore', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('merges snapshot history, REST gap events, and SSE buffer in id order', () => {
    const merged = mergeGraphActivityEvents(
      [event(1), event(3)],
      [event(5), event(4), event(3)],
      [event(6), event(4)],
    )

    expect(merged.map((item) => item.id)).toEqual([1, 3, 4, 5, 6])
  })

  it('buffers live events until snapshot hydration and applies only events after its cursor', () => {
    const store = useSocialGraphActivityStore()
    const apply = vi.fn()

    store.beginBuffering('sim-1')
    store.receive(event(4), apply)
    store.receive(event(7), apply)
    store.hydrateHistory([event(1), event(2), event(4)], 4)
    store.completeBuffering([event(5), event(6)], apply)

    expect(store.events.map((item) => item.id)).toEqual([1, 2, 4, 5, 6, 7])
    expect(apply.mock.calls.map(([item]) => item.id)).toEqual([5, 6, 7])
    expect(store.latestEventId).toBe(7)
    expect(store.cursorId).toBe(7)
    expect(store.isFollowingLive).toBe(true)
  })

  it('deduplicates reconnect events and preserves a detached replay cursor', () => {
    const store = useSocialGraphActivityStore()
    const apply = vi.fn()

    store.beginBuffering('sim-1')
    store.hydrateHistory([event(1), event(2), event(3)], 3)
    store.completeBuffering([], apply)
    store.setReplayCursor(2)
    store.receive(event(3), apply)
    store.receive(event(4), apply)

    expect(store.events.map((item) => item.id)).toEqual([1, 2, 3, 4])
    expect(apply).toHaveBeenCalledOnce()
    expect(store.cursorId).toBe(2)
    expect(store.isFollowingLive).toBe(false)

    store.returnToLive()
    expect(store.cursorId).toBe(4)
    expect(store.isFollowingLive).toBe(true)
  })
})
