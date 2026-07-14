import type { GraphActivityEvent } from '../api/client'

export function mergeGraphActivityEvents(
  ...groups: GraphActivityEvent[][]
): GraphActivityEvent[] {
  const byId = new Map<number, GraphActivityEvent>()
  for (const group of groups) {
    for (const event of group) byId.set(event.id, event)
  }
  return Array.from(byId.values()).sort((left, right) => left.id - right.id)
}
