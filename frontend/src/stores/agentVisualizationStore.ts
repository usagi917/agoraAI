import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type AgentVisualStatus = 'idle' | 'thinking' | 'executing' | 'speaking' | 'debating'

export interface RecentThought {
  agentId: string
  agentName: string
  reasoningChain: string
  chosenAction: string
  timestamp: number
}

export interface CommunicationFlow {
  sourceId: string
  targetId: string
  messageType: string
  content: string
  timestamp: number
}

export interface DialogueEvent {
  participantName: string
  argument: string
  round: number
  timestamp: number
}

export type TickerEventType = 'thought' | 'communication' | 'dialogue' | 'system'

export interface TickerEvent {
  id: string
  type: TickerEventType
  agentName: string
  summary: string
  timestamp: number
  icon: string
}

export interface SystemTickerEvent {
  icon: string
  label: string
  detail?: string
  timestamp: number
}

const MAX_RECENT_THOUGHTS = 20
const MAX_COMMUNICATION_FLOWS = 50
const MAX_DIALOGUE_EVENTS = 30
const MAX_SYSTEM_EVENTS = 30
const MAX_TICKER_EVENTS = 30
const THINKING_TIMEOUT_MS = 30_000

export const useAgentVisualizationStore = defineStore('agentVisualization', () => {
  const agentStatusMap = ref<Record<string, AgentVisualStatus>>({})
  const thinkingAgentId = ref<string | null>(null)
  const recentThoughts = ref<RecentThought[]>([])
  const communicationFlows = ref<CommunicationFlow[]>([])
  const dialogueEvents = ref<DialogueEvent[]>([])
  const systemEvents = ref<SystemTickerEvent[]>([])

  let _thinkingTimer: ReturnType<typeof setTimeout> | null = null

  const latestThought = computed(() =>
    recentThoughts.value.length > 0
      ? recentThoughts.value[recentThoughts.value.length - 1]
      : null,
  )

  const tickerEvents = computed<TickerEvent[]>(() => {
    const events: TickerEvent[] = []

    for (const t of recentThoughts.value) {
      events.push({
        id: `thought-${t.agentId}-${t.timestamp}`,
        type: 'thought',
        agentName: t.agentName,
        summary: t.chosenAction,
        timestamp: t.timestamp,
        icon: '◈',
      })
    }

    for (const f of communicationFlows.value) {
      events.push({
        id: `comm-${f.sourceId}-${f.timestamp}`,
        type: 'communication',
        agentName: f.sourceId,
        summary: f.content.slice(0, 80),
        timestamp: f.timestamp,
        icon: '↔',
      })
    }

    for (const d of dialogueEvents.value) {
      events.push({
        id: `dialogue-${d.participantName}-${d.timestamp}`,
        type: 'dialogue',
        agentName: d.participantName,
        summary: d.argument.slice(0, 80),
        timestamp: d.timestamp,
        icon: '◉',
      })
    }

    for (const s of systemEvents.value) {
      events.push({
        id: `sys-${s.timestamp}`,
        type: 'system',
        agentName: s.label,
        summary: s.detail || '',
        timestamp: s.timestamp,
        icon: s.icon,
      })
    }

    events.sort((a, b) => a.timestamp - b.timestamp)
    return events.slice(-MAX_TICKER_EVENTS)
  })

  function getAgentStatus(agentId: string): AgentVisualStatus {
    return agentStatusMap.value[agentId] || 'idle'
  }

  function setAgentStatus(agentId: string, status: AgentVisualStatus) {
    agentStatusMap.value[agentId] = status
  }

  function setThinkingAgent(agentId: string) {
    thinkingAgentId.value = agentId
    agentStatusMap.value[agentId] = 'thinking'

    if (_thinkingTimer) clearTimeout(_thinkingTimer)
    _thinkingTimer = setTimeout(() => {
      if (thinkingAgentId.value === agentId) {
        thinkingAgentId.value = null
        agentStatusMap.value[agentId] = 'idle'
      }
    }, THINKING_TIMEOUT_MS)
  }

  function clearThinkingAgent(agentId: string) {
    if (_thinkingTimer) {
      clearTimeout(_thinkingTimer)
      _thinkingTimer = null
    }
    if (thinkingAgentId.value === agentId) {
      thinkingAgentId.value = null
    }
    agentStatusMap.value[agentId] = 'idle'
  }

  function addRecentThought(thought: RecentThought) {
    recentThoughts.value.push(thought)
    if (recentThoughts.value.length > MAX_RECENT_THOUGHTS) {
      recentThoughts.value = recentThoughts.value.slice(-MAX_RECENT_THOUGHTS)
    }
  }

  function addCommunicationFlow(flow: CommunicationFlow) {
    communicationFlows.value.push(flow)
    if (communicationFlows.value.length > MAX_COMMUNICATION_FLOWS) {
      communicationFlows.value = communicationFlows.value.slice(-MAX_COMMUNICATION_FLOWS)
    }
  }

  function addDialogueEvent(event: { participantName: string; argument: string; round: number }) {
    dialogueEvents.value.push({
      ...event,
      timestamp: Date.now(),
    })
    if (dialogueEvents.value.length > MAX_DIALOGUE_EVENTS) {
      dialogueEvents.value = dialogueEvents.value.slice(-MAX_DIALOGUE_EVENTS)
    }
  }

  function addSystemEvent(icon: string, label: string, detail?: string) {
    systemEvents.value.push({
      icon,
      label,
      detail,
      timestamp: Date.now(),
    })
    if (systemEvents.value.length > MAX_SYSTEM_EVENTS) {
      systemEvents.value = systemEvents.value.slice(-MAX_SYSTEM_EVENTS)
    }
  }

  function reset() {
    if (_thinkingTimer) {
      clearTimeout(_thinkingTimer)
      _thinkingTimer = null
    }
    agentStatusMap.value = {}
    thinkingAgentId.value = null
    recentThoughts.value = []
    communicationFlows.value = []
    dialogueEvents.value = []
    systemEvents.value = []
  }

  return {
    agentStatusMap,
    thinkingAgentId,
    recentThoughts,
    communicationFlows,
    dialogueEvents,
    systemEvents,
    latestThought,
    tickerEvents,
    getAgentStatus,
    setAgentStatus,
    setThinkingAgent,
    clearThinkingAgent,
    addRecentThought,
    addCommunicationFlow,
    addDialogueEvent,
    addSystemEvent,
    reset,
  }
})
