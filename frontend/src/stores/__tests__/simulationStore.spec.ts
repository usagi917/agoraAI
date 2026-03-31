import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useSimulationStore } from '../simulationStore'

describe('simulationStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('updates the live opinion distribution when propagation completes', () => {
    const store = useSimulationStore()

    store.setOpinionDistribution({ 賛成: 0.7, 反対: 0.3 })
    store.setPropagationCompleted({
      converged: true,
      cluster_count: 2,
      clusters: [{ label: 0, size: 20, centroid: [0.9] }],
      echo_chamber: { homophily_index: 0.8, polarization_index: 0.4 },
      opinionDistribution: { 賛成: 0.58, 反対: 0.42 },
    })

    expect(store.propagationCompleted).toBe(true)
    expect(store.propagationClusters).toEqual([
      { label: 0, size: 20, centroid: [0.9] },
    ])
    expect(store.opinionDistribution).toEqual({ 賛成: 0.58, 反対: 0.42 })
  })
})
