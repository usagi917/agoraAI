import { describe, expect, it } from 'vitest'

import { createSwimMotionState, sampleSwimMotion } from '../forceGraphMotion'

function cloneState(id: string, importance = 0.5, type = 'agent') {
  return structuredClone(createSwimMotionState(id, importance, type))
}

describe('forceGraphMotion', () => {
  it('creates deterministic swim state per node id', () => {
    const a = createSwimMotionState('agent-12', 0.65, 'agent')
    const b = createSwimMotionState('agent-12', 0.65, 'agent')

    expect(a).toEqual(b)
  })

  it('keeps important agent motion slightly tighter', () => {
    const regular = createSwimMotionState('agent-regular', 0.55, 'agent')
    const council = createSwimMotionState('agent-council', 0.95, 'agent')

    expect(council.lateralAmplitude).toBeLessThan(regular.lateralAmplitude)
    expect(council.verticalAmplitude).toBeLessThan(regular.verticalAmplitude)
  })

  it('samples a finite fish-like offset and preserves deterministic output for equal state', () => {
    const stateA = cloneState('agent-7', 0.72)
    const stateB = cloneState('agent-7', 0.72)

    const input = {
      coords: { x: 24, y: -6, z: 18 },
      velocity: { x: 0.9, y: 0.15, z: -0.4 },
      time: 12.5,
    }

    const sampleA = sampleSwimMotion({ ...input, state: stateA, activity: 0.4 })
    const sampleB = sampleSwimMotion({ ...input, state: stateB, activity: 0.4 })

    expect(sampleA).toEqual(sampleB)
    expect(Number.isFinite(sampleA.offset.x)).toBe(true)
    expect(Number.isFinite(sampleA.offset.y)).toBe(true)
    expect(Number.isFinite(sampleA.offset.z)).toBe(true)
    expect(Math.hypot(sampleA.offset.x, sampleA.offset.y, sampleA.offset.z)).toBeGreaterThan(0.1)
    expect(Math.hypot(sampleA.heading.x, sampleA.heading.y, sampleA.heading.z)).toBeCloseTo(1, 5)
  })
})
