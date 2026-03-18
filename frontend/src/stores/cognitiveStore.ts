import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface AgentBDIState {
  agentId: string
  agentName: string
  round: number
  beliefs: Array<{ proposition: string; confidence: number }>
  desires: Array<{ goal_text: string; priority: number }>
  intentions: Array<{ plan_text: string; commitment_strength: number }>
  actionTaken: string
  reasoningChain: string
  trustMap: Record<string, number>
  mentalModels: Record<string, any>
}

export interface MemoryEntry {
  id: string
  agentId: string
  memoryType: 'episodic' | 'semantic' | 'procedural'
  content: string
  importance: number
  round: number
  isReflection: boolean
  reflectionLevel: number
}

export interface ReflectionEntry {
  insight: string
  importance: number
  level: number
  sourceIds: string[]
  round: number
}

export interface ToMRelation {
  observer: string
  target: string
  inferredGoals: string[]
  predictedAction: string
  trustLevel: number
  confidence: number
}

export const useCognitiveStore = defineStore('cognitive', () => {
  // BDI 状態
  const agentStates = ref<Record<string, AgentBDIState>>({})
  const selectedAgentId = ref<string | null>(null)

  // 記憶
  const memoryEntries = ref<MemoryEntry[]>([])
  const reflections = ref<ReflectionEntry[]>([])

  // Theory of Mind
  const tomRelations = ref<ToMRelation[]>([])

  // 社会ネットワーク
  const socialNetwork = ref<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] })
  const coalitions = ref<string[][]>([])

  // 認知モード
  const cognitiveMode = ref<'legacy' | 'advanced'>('legacy')

  // 算出プロパティ
  const selectedAgent = computed(() =>
    selectedAgentId.value ? agentStates.value[selectedAgentId.value] : null,
  )

  const agentList = computed(() => Object.values(agentStates.value))

  const selectedAgentMemories = computed(() => {
    if (!selectedAgentId.value) return []
    return memoryEntries.value.filter(m => m.agentId === selectedAgentId.value)
  })

  const selectedAgentReflections = computed(() => {
    if (!selectedAgentId.value) return []
    return reflections.value.filter(r =>
      memoryEntries.value.some(
        m => m.agentId === selectedAgentId.value && m.isReflection,
      ),
    )
  })

  // アクション
  function updateAgentState(state: AgentBDIState) {
    agentStates.value[state.agentId] = state
  }

  function selectAgent(agentId: string | null) {
    selectedAgentId.value = agentId
  }

  function addMemoryEntry(entry: MemoryEntry) {
    memoryEntries.value.push(entry)
  }

  function addReflection(reflection: ReflectionEntry) {
    reflections.value.push(reflection)
  }

  function updateToMRelations(relations: ToMRelation[]) {
    tomRelations.value = relations
  }

  function updateSocialNetwork(network: { nodes: any[]; edges: any[] }) {
    socialNetwork.value = network
  }

  function updateCoalitions(groups: string[][]) {
    coalitions.value = groups
  }

  function setCognitiveMode(mode: 'legacy' | 'advanced') {
    cognitiveMode.value = mode
  }

  return {
    agentStates,
    selectedAgentId,
    memoryEntries,
    reflections,
    tomRelations,
    socialNetwork,
    coalitions,
    cognitiveMode,
    selectedAgent,
    agentList,
    selectedAgentMemories,
    selectedAgentReflections,
    updateAgentState,
    selectAgent,
    addMemoryEntry,
    addReflection,
    updateToMRelations,
    updateSocialNetwork,
    updateCoalitions,
    setCognitiveMode,
  }
})
