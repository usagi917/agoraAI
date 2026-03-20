import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ActivityLevel = 'info' | 'event' | 'phase' | 'error' | 'agent'

export interface ActivityEntry {
  id: number
  timestamp: number
  level: ActivityLevel
  icon: string
  message: string
  detail?: string
  agentName?: string
  round?: number
  track?: 'phase' | 'timeline' | 'agent' | 'graph' | 'report' | 'swarm'
  status?: 'pending' | 'running' | 'completed' | 'failed'
}

const MAX_ENTRIES = 200
let nextId = 0

export const useActivityStore = defineStore('activity', () => {
  const entries = ref<ActivityEntry[]>([])

  function addEntry(
    level: ActivityLevel,
    icon: string,
    message: string,
    options?: {
      detail?: string
      agentName?: string
      round?: number
      track?: ActivityEntry['track']
      status?: ActivityEntry['status']
      timestamp?: number
    },
  ) {
    entries.value.push({
      id: nextId++,
      timestamp: options?.timestamp ?? Date.now(),
      level,
      icon,
      message,
      ...options,
    })
    if (entries.value.length > MAX_ENTRIES) {
      entries.value.splice(0, entries.value.length - MAX_ENTRIES)
    }
  }

  function replaceEntries(nextEntries: ActivityEntry[]) {
    entries.value = nextEntries.map((entry, index) => ({
      ...entry,
      id: entry.id ?? index,
    }))
    nextId = entries.value.reduce((maxId, entry) => Math.max(maxId, entry.id), -1) + 1
  }

  function toSnapshot() {
    return entries.value.map((entry) => ({ ...entry }))
  }

  function clear() {
    entries.value = []
  }

  return { entries, addEntry, replaceEntries, toSnapshot, clear }
})
