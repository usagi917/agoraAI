import { describe, expect, it, vi, beforeEach } from 'vitest'

// Mock THREE.js to avoid WebGL dependency in tests
vi.mock('three', () => {
  function MockVector3(x = 0, y = 0, z = 0) {
    return {
      x, y, z,
      addVectors: vi.fn().mockReturnThis(),
      multiplyScalar: vi.fn().mockReturnThis(),
      distanceTo: vi.fn().mockReturnValue(0),
    }
  }

  function createMockGeometry() {
    return {
      dispose: vi.fn(),
      setAttribute: vi.fn(),
      attributes: {
        position: { setXYZ: vi.fn(), needsUpdate: false },
      },
    }
  }

  function createMockMaterial() {
    return {
      dispose: vi.fn(),
      color: { set: vi.fn() },
      opacity: 0,
      transparent: true,
      depthWrite: false,
      blending: 0,
    }
  }

  class Group {
    name = ''
    add = vi.fn()
  }

  class Mesh {
    geometry = createMockGeometry()
    material = createMockMaterial()
    visible = false
  }

  class Points {
    geometry = createMockGeometry()
    material = createMockMaterial()
    visible = false
  }

  class MeshBasicMaterial {
    color = { set: vi.fn() }
    opacity = 0
    transparent = true
    depthWrite = false
    blending = 0
    dispose = vi.fn()
  }

  class PointsMaterial {
    color = { set: vi.fn() }
    opacity = 0
    size = 1
    transparent = true
    depthWrite = false
    blending = 0
    dispose = vi.fn()
  }

  class BufferGeometry {
    dispose = vi.fn()
    setAttribute = vi.fn()
    attributes = { position: { setXYZ: vi.fn(), needsUpdate: false } }
  }

  class BufferAttribute {}

  class TubeGeometry extends BufferGeometry {}

  class QuadraticBezierCurve3 {
    v0 = { x: 0, y: 0, z: 0, distanceTo: vi.fn().mockReturnValue(0) }
    getPoint = vi.fn().mockReturnValue({ x: 0, y: 0, z: 0 })
  }

  return {
    Group,
    Mesh,
    Points,
    MeshBasicMaterial,
    PointsMaterial,
    BufferGeometry,
    BufferAttribute,
    TubeGeometry,
    QuadraticBezierCurve3,
    AdditiveBlending: 2,
    Vector3: MockVector3,
  }
})

import { ref } from 'vue'
import { useCommunicationPulse } from '../useCommunicationPulse'

function createMockGraph() {
  return ref({
    scene: () => ({
      add: vi.fn(),
      remove: vi.fn(),
    }),
  } as any)
}

function createMockNodes() {
  return () => [
    { id: 'agent-1', x: 0, y: 0, z: 0 },
    { id: 'agent-2', x: 10, y: 0, z: 0 },
    { id: 'agent-3', x: 5, y: 5, z: 0 },
  ]
}

describe('useCommunicationPulse', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('creates a pulse composable with expected API', () => {
    const graphRef = createMockGraph()
    const getNodes = createMockNodes()

    const pulse = useCommunicationPulse(graphRef, getNodes)

    expect(pulse.addPulseLine).toBeInstanceOf(Function)
    expect(pulse.update).toBeInstanceOf(Function)
    expect(pulse.dispose).toBeInstanceOf(Function)
  })

  it('addPulseLine returns true when both nodes exist', () => {
    const graphRef = createMockGraph()
    const getNodes = createMockNodes()

    const pulse = useCommunicationPulse(graphRef, getNodes)
    const result = pulse.addPulseLine('agent-1', 'agent-2', 'communication')

    expect(result).toBe(true)
  })

  it('addPulseLine returns false when source node is missing', () => {
    const graphRef = createMockGraph()
    const getNodes = createMockNodes()

    const pulse = useCommunicationPulse(graphRef, getNodes)
    const result = pulse.addPulseLine('nonexistent', 'agent-2', 'communication')

    expect(result).toBe(false)
  })

  it('addPulseLine returns false when pool is exhausted', () => {
    const graphRef = createMockGraph()
    const getNodes = createMockNodes()

    const pulse = useCommunicationPulse(graphRef, getNodes)

    // Fill the pool (size = 20)
    for (let i = 0; i < 20; i++) {
      pulse.addPulseLine('agent-1', 'agent-2', 'communication')
    }

    const result = pulse.addPulseLine('agent-1', 'agent-2', 'communication')
    expect(result).toBe(false)
  })

  it('dispose cleans up all resources', () => {
    const graphRef = createMockGraph()
    const getNodes = createMockNodes()

    const pulse = useCommunicationPulse(graphRef, getNodes)
    pulse.addPulseLine('agent-1', 'agent-2', 'thinking')

    // Should not throw
    expect(() => pulse.dispose()).not.toThrow()
  })
})
