import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type SimulationMode = 'single' | 'swarm' | 'hybrid' | 'pm_board'

export interface ColonyState {
  id: string
  colonyIndex: number
  perspectiveId: string
  perspectiveLabel: string
  temperature: number
  adversarial: boolean
  status: string
  currentRound: number
  totalRounds: number
  eventCount: number
}

export const useSimulationStore = defineStore('simulation', () => {
  // 基本状態
  const simulationId = ref<string | null>(null)
  const mode = ref<SimulationMode>('single')
  const status = ref<string>('idle')
  const phase = ref<string>('queued')
  const error = ref('')
  const promptText = ref('')

  // Single モード状態
  const currentRound = ref(0)
  const totalRounds = ref(0)

  // Swarm/Hybrid モード状態
  const colonies = ref<ColonyState[]>([])

  // 算出プロパティ
  const completedColonies = computed(() =>
    colonies.value.filter(c => c.status === 'completed').length,
  )

  const progress = computed(() => {
    if (status.value === 'completed') return 1

    if (mode.value === 'single') {
      if (totalRounds.value === 0) return 0.05
      return Math.min(0.85, currentRound.value / totalRounds.value * 0.8 + 0.1)
    }

    // swarm/hybrid
    if (colonies.value.length === 0) return 0.05
    return completedColonies.value / colonies.value.length
  })

  const isSwarmMode = computed(() => mode.value === 'swarm' || mode.value === 'hybrid')

  // アクション
  function init(id: string, simMode: SimulationMode, prompt: string = '') {
    simulationId.value = id
    mode.value = simMode
    promptText.value = prompt
    status.value = 'connecting'
    phase.value = 'queued'
    currentRound.value = 0
    totalRounds.value = 0
    colonies.value = []
    error.value = ''
  }

  function setStatus(s: string) {
    status.value = s
  }

  function setPhase(p: string) {
    phase.value = p
  }

  function setError(msg: string) {
    error.value = msg
    status.value = 'failed'
  }

  function setRound(round: number, total?: number) {
    currentRound.value = round
    if (total !== undefined) totalRounds.value = total
  }

  function setColonies(colonyList: ColonyState[]) {
    colonies.value = colonyList
  }

  function updateColonyStatus(colonyId: string, newStatus: string, extra?: Partial<ColonyState>) {
    const colony = colonies.value.find(c => c.id === colonyId)
    if (colony) {
      colony.status = newStatus
      if (extra) Object.assign(colony, extra)
    }
  }

  return {
    simulationId,
    mode,
    status,
    phase,
    error,
    promptText,
    currentRound,
    totalRounds,
    colonies,
    completedColonies,
    progress,
    isSwarmMode,
    init,
    setStatus,
    setPhase,
    setError,
    setRound,
    setColonies,
    updateColonyStatus,
  }
})
