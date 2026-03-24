const TAU = Math.PI * 2

export interface MotionVector {
  x: number
  y: number
  z: number
}

export interface SwimMotionState {
  phase: number
  bobPhase: number
  flowPhase: number
  speed: number
  lateralAmplitude: number
  verticalAmplitude: number
  forwardAmplitude: number
  bankAmplitude: number
  driftAmplitude: number
  headingSmoothing: number
  heading: MotionVector
  previousVelocity: MotionVector
}

export interface SwimMotionSample {
  offset: MotionVector
  heading: MotionVector
  yaw: number
  pitch: number
  roll: number
  thrust: number
}

interface SwimMotionInput {
  coords: MotionVector
  velocity: MotionVector
  time: number
  state: SwimMotionState
  activity?: number
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function length(vector: MotionVector) {
  return Math.sqrt(vector.x * vector.x + vector.y * vector.y + vector.z * vector.z)
}

function scale(vector: MotionVector, factor: number): MotionVector {
  return {
    x: vector.x * factor,
    y: vector.y * factor,
    z: vector.z * factor,
  }
}

function add(...vectors: MotionVector[]): MotionVector {
  return vectors.reduce(
    (sum, vector) => ({
      x: sum.x + vector.x,
      y: sum.y + vector.y,
      z: sum.z + vector.z,
    }),
    { x: 0, y: 0, z: 0 },
  )
}

function lerpVector(from: MotionVector, to: MotionVector, alpha: number): MotionVector {
  return {
    x: from.x + (to.x - from.x) * alpha,
    y: from.y + (to.y - from.y) * alpha,
    z: from.z + (to.z - from.z) * alpha,
  }
}

function normalize(vector: MotionVector, fallback: MotionVector): MotionVector {
  const len = length(vector)
  if (len < 1e-5) return { ...fallback }
  return scale(vector, 1 / len)
}

function cross(a: MotionVector, b: MotionVector): MotionVector {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  }
}

function hashToUnit(seed: string, salt: number) {
  let hash = 2166136261 ^ salt
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return ((hash >>> 0) % 10000) / 10000
}

export function createSwimMotionState(
  id: string,
  importanceScore: number,
  type: string,
): SwimMotionState {
  const isCouncilScale = type === 'agent' && importanceScore > 0.8
  const amplitudeScale = isCouncilScale ? 0.82 : 1
  const headingSeed = hashToUnit(id, 11) * TAU

  return {
    phase: hashToUnit(id, 1) * TAU,
    bobPhase: hashToUnit(id, 2) * TAU,
    flowPhase: hashToUnit(id, 3) * TAU,
    speed: 1.35 + hashToUnit(id, 4) * 0.85 + (type === 'agent' ? 0.15 : 0),
    lateralAmplitude: amplitudeScale * (1.2 + hashToUnit(id, 5) * 1.5),
    verticalAmplitude: amplitudeScale * (0.45 + hashToUnit(id, 6) * 0.95),
    forwardAmplitude: amplitudeScale * (0.2 + hashToUnit(id, 7) * 0.45),
    bankAmplitude: 0.14 + hashToUnit(id, 8) * 0.18,
    driftAmplitude: amplitudeScale * (0.3 + hashToUnit(id, 9) * 0.55),
    headingSmoothing: isCouncilScale ? 0.08 : 0.12,
    heading: {
      x: Math.cos(headingSeed),
      y: 0,
      z: Math.sin(headingSeed),
    },
    previousVelocity: { x: 0, y: 0, z: 0 },
  }
}

export function sampleSwimMotion({
  coords,
  velocity,
  time,
  state,
  activity = 0,
}: SwimMotionInput): SwimMotionSample {
  const prevVelocity = state.previousVelocity
  const activityBoost = clamp(activity, 0, 1)

  const localFlow = {
    x: Math.sin(coords.z * 0.018 + time * 0.55 + state.flowPhase) * 0.7,
    y: Math.sin(coords.x * 0.013 + time * 0.35 + state.bobPhase) * 0.18,
    z: Math.cos(coords.x * 0.016 - time * 0.5 + state.phase) * 0.7,
  }

  const velocityIntent = scale(velocity, 1.1 + activityBoost * 0.3)
  const driftIntent = scale(localFlow, 0.85 + activityBoost * 0.15)
  const idleHeading = {
    x: Math.cos(state.phase),
    y: Math.sin(state.bobPhase) * 0.08,
    z: Math.sin(state.phase),
  }
  const desiredHeading = normalize(
    add(velocityIntent, driftIntent, scale(idleHeading, 0.8)),
    state.heading,
  )

  const heading = normalize(
    lerpVector(state.heading, desiredHeading, state.headingSmoothing + activityBoost * 0.03),
    state.heading,
  )
  state.heading = heading

  const worldUp = Math.abs(heading.y) > 0.92
    ? { x: 1, y: 0, z: 0 }
    : { x: 0, y: 1, z: 0 }
  const lateral = normalize(cross(worldUp, heading), { x: 1, y: 0, z: 0 })
  const vertical = normalize(cross(heading, lateral), { x: 0, y: 1, z: 0 })

  const swimPhase = time * state.speed + state.phase
  const lateralWave = Math.sin(swimPhase) + 0.32 * Math.sin(swimPhase * 2.25 + state.flowPhase)
  const verticalWave = Math.sin(swimPhase * 0.6 + state.bobPhase)
  const thrustWave = 0.5 + 0.5 * Math.sin(swimPhase * 2.1 + state.phase)
  const driftWave = Math.sin(time * 0.24 + state.flowPhase)

  const offset = add(
    scale(lateral, state.lateralAmplitude * lateralWave),
    scale(vertical, state.verticalAmplitude * verticalWave),
    scale(heading, state.forwardAmplitude * thrustWave),
    scale(localFlow, state.driftAmplitude * driftWave),
  )

  const horizontalLength = Math.hypot(heading.x, heading.z) || 1e-5
  const yaw = Math.atan2(heading.x, heading.z)
  const pitch = Math.atan2(heading.y, horizontalLength) + verticalWave * 0.08
  const turnDelta = cross(prevVelocity, velocity).y
  const roll = clamp(
    lateralWave * state.bankAmplitude + turnDelta * 0.035,
    -0.55,
    0.55,
  )

  state.previousVelocity = { ...velocity }

  return {
    offset,
    heading,
    yaw,
    pitch,
    roll,
    thrust: thrustWave,
  }
}
