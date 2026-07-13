import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import type { GraphActivityEvent } from '../api/client'
import { mergeGraphActivityEvents } from '../services/graphActivityMerge'

type EventApplier = (event: GraphActivityEvent) => unknown

export const useSocialGraphActivityStore = defineStore('socialGraphActivity', () => {
  const simulationId = ref('')
  const events = ref<GraphActivityEvent[]>([])
  const bufferedEvents = ref<GraphActivityEvent[]>([])
  const isBuffering = ref(false)
  const latestEventId = ref(0)
  const cursorId = ref(0)
  const isFollowingLive = ref(true)
  const selectedEventId = ref<number | null>(null)
  const knownIds = new Set<number>()

  const selectedEvent = computed(() => (
    selectedEventId.value == null
      ? null
      : events.value.find((event) => event.id === selectedEventId.value) ?? null
  ))
  const visibleEvents = computed(() => events.value.filter((event) => event.id <= cursorId.value))
  const changedCount = computed(() => visibleEvents.value.filter((event) => (
    event.kind === 'stance_shift' || event.kind === 'relationship_changed'
  )).length)

  function reset(nextSimulationId = '') {
    simulationId.value = nextSimulationId
    events.value = []
    bufferedEvents.value = []
    isBuffering.value = false
    latestEventId.value = 0
    cursorId.value = 0
    isFollowingLive.value = true
    selectedEventId.value = null
    knownIds.clear()
  }

  function beginBuffering(nextSimulationId: string) {
    if (simulationId.value !== nextSimulationId) reset(nextSimulationId)
    bufferedEvents.value = []
    isBuffering.value = true
  }

  function insertEvents(incoming: GraphActivityEvent[]) {
    const additions = incoming.filter((event) => {
      if (knownIds.has(event.id)) return false
      knownIds.add(event.id)
      return true
    })
    if (!additions.length) return []
    events.value = mergeGraphActivityEvents(events.value, additions)
    latestEventId.value = Math.max(latestEventId.value, ...additions.map((event) => event.id))
    return additions
  }

  function receive(event: GraphActivityEvent, apply: EventApplier) {
    if (event.simulation_id !== simulationId.value) return false
    if (isBuffering.value) {
      bufferedEvents.value = mergeGraphActivityEvents(bufferedEvents.value, [event])
      return true
    }
    const additions = insertEvents([event])
    if (!additions.length) return false
    apply(event)
    if (isFollowingLive.value) cursorId.value = latestEventId.value
    return true
  }

  function hydrateHistory(history: GraphActivityEvent[], snapshotEventId: number) {
    events.value = mergeGraphActivityEvents(history.filter((event) => event.id <= snapshotEventId))
    knownIds.clear()
    events.value.forEach((event) => knownIds.add(event.id))
    latestEventId.value = events.value.at(-1)?.id ?? snapshotEventId
    latestEventId.value = Math.max(latestEventId.value, snapshotEventId)
    cursorId.value = snapshotEventId
    isFollowingLive.value = true
  }

  function completeBuffering(restEvents: GraphActivityEvent[], apply: EventApplier) {
    const snapshotEventId = cursorId.value
    const candidates = mergeGraphActivityEvents(restEvents, bufferedEvents.value)
    const additions = insertEvents(candidates)
    for (const event of additions.filter((item) => item.id > snapshotEventId)) apply(event)
    bufferedEvents.value = []
    isBuffering.value = false
    if (isFollowingLive.value) cursorId.value = latestEventId.value
  }

  function setReplayCursor(eventId: number) {
    const bounded = Math.max(0, Math.min(eventId, latestEventId.value))
    cursorId.value = bounded
    selectedEventId.value = bounded || null
    isFollowingLive.value = bounded === latestEventId.value
  }

  function selectEvent(eventId: number) {
    selectedEventId.value = eventId
    setReplayCursor(eventId)
  }

  function returnToLive() {
    cursorId.value = latestEventId.value
    selectedEventId.value = latestEventId.value || null
    isFollowingLive.value = true
  }

  return {
    simulationId,
    events,
    bufferedEvents,
    isBuffering,
    latestEventId,
    cursorId,
    isFollowingLive,
    selectedEventId,
    selectedEvent,
    visibleEvents,
    changedCount,
    beginBuffering,
    receive,
    hydrateHistory,
    completeBuffering,
    setReplayCursor,
    selectEvent,
    returnToLive,
    reset,
  }
})
