import type { GraphActivityEvent } from '../api/client'
import { useSocialGraphActivityStore } from '../stores/socialGraphActivityStore'
import { useSocialGraphTopologyStore } from '../stores/socialGraphTopologyStore'
import { useSocialGraphViewStore } from '../stores/socialGraphViewStore'
import { useSocietyGraphStore } from '../stores/societyGraphStore'

export function applyGraphActivityEventToStores(event: GraphActivityEvent) {
  useSocialGraphTopologyStore().applyEvent(event)
  useSocietyGraphStore().applyGraphActivityEvent(event)
}

export function handleGraphActivityEvent(event: GraphActivityEvent) {
  const activity = useSocialGraphActivityStore()
  activity.receive(event, applyGraphActivityEventToStores)
}

export function focusGraphActivityEvent(event: GraphActivityEvent) {
  const edgeId = event.edge_id && useSocialGraphTopologyStore().edges.has(event.edge_id)
    ? event.edge_id
    : null
  useSocialGraphViewStore().focusEvent(event.source_id, edgeId)
}
