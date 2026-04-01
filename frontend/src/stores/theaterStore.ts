import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface TheaterClaim {
  agentId: string
  claimText: string
  stance: string
  confidence: number
  timestamp: number
}

export interface TheaterStanceShift {
  agentId: string
  fromStance: string
  toStance: string
  reason: string
  timestamp: number
}

export interface TheaterAlliance {
  agentIds: string[]
  stance: string
  strength: number
  timestamp: number
}

export interface TheaterDecision {
  decisionText: string
  confidence: number
  dissentCount: number
  timestamp: number
}

export const useTheaterStore = defineStore('theater', () => {
  const claims = ref<TheaterClaim[]>([])
  const stanceShifts = ref<TheaterStanceShift[]>([])
  const alliances = ref<TheaterAlliance[]>([])
  const decision = ref<TheaterDecision | null>(null)

  const MAX_CLAIMS = 50

  const latestClaim = computed(() => claims.value[claims.value.length - 1] ?? null)
  const latestShift = computed(() => stanceShifts.value[stanceShifts.value.length - 1] ?? null)
  const latestAlliance = computed(() => alliances.value[alliances.value.length - 1] ?? null)

  function addClaim(claim: Omit<TheaterClaim, 'timestamp'>) {
    claims.value.push({ ...claim, timestamp: Date.now() })
    if (claims.value.length > MAX_CLAIMS) {
      claims.value = claims.value.slice(-MAX_CLAIMS)
    }
  }

  function addStanceShift(shift: Omit<TheaterStanceShift, 'timestamp'>) {
    stanceShifts.value.push({ ...shift, timestamp: Date.now() })
  }

  function setAlliances(newAlliances: Omit<TheaterAlliance, 'timestamp'>[]) {
    alliances.value = newAlliances.map(a => ({ ...a, timestamp: Date.now() }))
  }

  function setDecision(d: Omit<TheaterDecision, 'timestamp'>) {
    decision.value = { ...d, timestamp: Date.now() }
  }

  function reset() {
    claims.value = []
    stanceShifts.value = []
    alliances.value = []
    decision.value = null
  }

  return {
    claims,
    stanceShifts,
    alliances,
    decision,
    latestClaim,
    latestShift,
    latestAlliance,
    addClaim,
    addStanceShift,
    setAlliances,
    setDecision,
    reset,
  }
})
