import {
  getGraphEvents,
  getGraphState,
  type GraphActivityEvent,
} from '../api/client'
import { useSocialGraphActivityStore } from '../stores/socialGraphActivityStore'
import { useSocialGraphTopologyStore } from '../stores/socialGraphTopologyStore'
import { applyGraphActivityEventToStores } from './graphActivityAdapter'
import { mergeGraphActivityEvents } from './graphActivityMerge'

const EVENT_PAGE_SIZE = 1000

export { mergeGraphActivityEvents } from './graphActivityMerge'

async function fetchHistoryThrough(
  simulationId: string,
  throughId: number,
  signal?: AbortSignal,
) {
  const history: GraphActivityEvent[] = []
  let afterId = 0
  while (afterId < throughId) {
    const page = await getGraphEvents(simulationId, {
      afterId,
      limit: EVENT_PAGE_SIZE,
      signal,
    })
    if (!page.length) break
    history.push(...page.filter((event) => event.id <= throughId))
    afterId = page.at(-1)?.id ?? afterId
    if (page.length < EVENT_PAGE_SIZE) break
  }
  return mergeGraphActivityEvents(history)
}

export async function bootstrapGraphActivity(
  simulationId: string,
  options?: { signal?: AbortSignal; bufferingStarted?: boolean },
) {
  const activity = useSocialGraphActivityStore()
  const topology = useSocialGraphTopologyStore()
  if (!options?.bufferingStarted) activity.beginBuffering(simulationId)

  const snapshot = await getGraphState(simulationId, { signal: options?.signal })
  topology.hydrate(snapshot)
  const history = await fetchHistoryThrough(
    simulationId,
    snapshot.latest_event_id,
    options?.signal,
  )
  activity.hydrateHistory(history, snapshot.latest_event_id)
  const gapEvents = await getGraphEvents(simulationId, {
    afterId: snapshot.latest_event_id,
    limit: EVENT_PAGE_SIZE,
    signal: options?.signal,
  })
  activity.completeBuffering(gapEvents, applyGraphActivityEventToStores)
  return snapshot
}
