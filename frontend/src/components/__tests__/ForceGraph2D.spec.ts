import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'

class MockForceGraph {
  static lastInstance: MockForceGraph | null = null
  callbacks: Record<string, (...args: unknown[]) => unknown> = {}
  setterCalls: Record<string, unknown[]> = {}
  graphDataValue: { nodes: unknown[]; links: unknown[] } = { nodes: [], links: [] }
  graphDataCalls = 0
  d3ForceCalls = 0
  reheatCalls = 0
  destructorCalled = false

  constructor(_el: HTMLElement) {
    MockForceGraph.lastInstance = this
    const self = this
    const handler: ProxyHandler<MockForceGraph> = {
      get(target, prop: string | symbol) {
        if (prop === 'graphDataValue') return self.graphDataValue
        if (prop === 'setterCalls') return self.setterCalls
        if (prop === 'graphDataCalls') return self.graphDataCalls
        if (prop === 'callbacks') return self.callbacks
        if (prop === 'destructorCalled') return self.destructorCalled
        if (prop === '_destructor') return () => { self.destructorCalled = true }
        if (prop === 'graphData') {
          return (data?: { nodes: unknown[]; links: unknown[] }) => {
            if (data !== undefined) {
              self.graphDataCalls += 1
              self.graphDataValue = data
            }
            return proxy
          }
        }
        if (prop === 'd3ForceCalls') return self.d3ForceCalls
        if (prop === 'reheatCalls') return self.reheatCalls
        if (prop === 'd3Force') {
          return (..._args: unknown[]) => {
            self.d3ForceCalls += 1
            return {
              strength: () => undefined,
              distance: () => undefined,
              distanceMax: () => undefined,
              radius: () => undefined,
              iterations: () => undefined,
            }
          }
        }
        if (prop === 'd3ReheatSimulation') {
          return () => {
            self.reheatCalls += 1
            return proxy
          }
        }
        if (prop === 'zoomToFit') return () => proxy
        if (prop === 'centerAt') return () => proxy
        if (prop === 'width' || prop === 'height') return () => proxy
        if (typeof prop === 'string' && prop.startsWith('on')) {
          return (cb: (...args: unknown[]) => unknown) => {
            self.callbacks[prop] = cb
            return proxy
          }
        }
        // Default: any other chainable setter returns self.
        return Reflect.get(target, prop) ?? ((...args: unknown[]) => {
          if (typeof prop === 'string') self.setterCalls[prop] = args
          return proxy
        })
      },
    }
    const proxy = new Proxy(this, handler)
    return proxy as unknown as this
  }
}

vi.mock('force-graph', () => ({ default: MockForceGraph }))

describe('ForceGraph2D', () => {
  beforeEach(() => {
    MockForceGraph.lastInstance = null
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function mountComponent(props: Record<string, unknown> = {}) {
    const ForceGraph2D = (await import('../ForceGraph2D.vue')).default
    return mount(ForceGraph2D, {
      props: {
        nodes: [],
        edges: [],
        ...props,
      },
    })
  }

  it('mounts a host div with data-testid="graph-2d"', async () => {
    const wrapper = await mountComponent()
    await flushPromises()
    expect(wrapper.find('[data-testid="graph-2d"]').exists()).toBe(true)
  })

  it('feeds graphData with the provided nodes and edges', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'organization', importance_score: 0.8, activity_score: 0 },
        { id: 'n2', label: 'Bob', type: 'person', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.7 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance
    expect(inst).toBeTruthy()
    expect(inst!.graphDataValue.nodes).toHaveLength(2)
    expect(inst!.graphDataValue.links).toHaveLength(1)
    expect((inst!.graphDataValue.nodes[0] as { id: string }).id).toBe('n1')
    void wrapper
  })

  it('uses finite simulation cooldowns so the engine can stop', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'organization', importance_score: 0.8, activity_score: 0 },
      ],
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    expect(inst.setterCalls.cooldownTicks?.[0]).toBeTypeOf('number')
    expect(inst.setterCalls.cooldownTicks?.[0]).not.toBe(Infinity)
    expect(inst.setterCalls.cooldownTime?.[0]).toBeTypeOf('number')
    expect(inst.setterCalls.cooldownTime?.[0]).not.toBe(Infinity)
    void wrapper
  })

  it('refreshes graphData when graph arrays are mutated in place', async () => {
    const ForceGraph2D = (await import('../ForceGraph2D.vue')).default
    const Parent = defineComponent({
      components: { ForceGraph2D },
      setup() {
        const nodes = ref([
          { id: 'n1', label: 'Alice', type: 'organization', importance_score: 0.8, activity_score: 0 },
        ])
        const edges = ref<unknown[]>([])
        return { nodes, edges }
      },
      template: '<ForceGraph2D :nodes="nodes" :edges="edges" />',
    })

    const wrapper = mount(Parent)
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const initialCalls = inst.graphDataCalls
    wrapper.vm.nodes.push({ id: 'n2', label: 'Bob', type: 'person', importance_score: 0.5, activity_score: 0 })
    await nextTick()
    await flushPromises()

    expect(inst.graphDataCalls).toBeGreaterThan(initialCalls)
    expect(inst.graphDataValue.nodes).toHaveLength(2)
  })

  it('emits select-node when onNodeClick fires (single click)', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'organization', importance_score: 0.8, activity_score: 0 },
      ],
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const node = inst.graphDataValue.nodes[0]
    const click = inst.callbacks.onNodeClick
    expect(click).toBeTypeOf('function')
    click(node, { detail: 1 } as unknown as MouseEvent)

    const emitted = wrapper.emitted('select-node')
    expect(emitted).toBeTruthy()
    expect((emitted![0][0] as { id: string }).id).toBe('n1')
    // Force-graph internal fields must not leak into the emit payload.
    expect(emitted![0][0]).not.toHaveProperty('vx')
    expect(emitted![0][0]).not.toHaveProperty('index')
  })

  it('does not emit select-node on double click but releases pinned position', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'organization', importance_score: 0.8, activity_score: 0 },
      ],
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const node = inst.graphDataValue.nodes[0] as { fx?: number; fy?: number }
    node.fx = 10
    node.fy = 20
    inst.callbacks.onNodeClick(node, { detail: 2 } as unknown as MouseEvent)

    expect(wrapper.emitted('select-node')).toBeFalsy()
    expect(node.fx).toBeUndefined()
    expect(node.fy).toBeUndefined()
  })

  it('pins node position on drag end', async () => {
    await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'organization', importance_score: 0.8, activity_score: 0 },
      ],
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const node = inst.graphDataValue.nodes[0] as { x: number; y: number; fx?: number; fy?: number }
    node.x = 42
    node.y = 84
    inst.callbacks.onNodeDragEnd(node, { x: 0, y: 0 })

    expect(node.fx).toBe(42)
    expect(node.fy).toBe(84)
  })

  it('emits hover-edge with flattened endpoints when onLinkHover fires', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'organization', importance_score: 0.5, activity_score: 0 },
        { id: 'n2', label: 'B', type: 'person', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.5 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const link = inst.graphDataValue.links[0] as { source: unknown; target: unknown }
    // Force-graph replaces string ids with node objects after layout.
    link.source = { id: 'n1' }
    link.target = { id: 'n2' }
    inst.callbacks.onLinkHover(link, null)

    const emitted = wrapper.emitted('hover-edge')
    expect(emitted).toBeTruthy()
    const payload = emitted![0][0] as { source: string; target: string }
    expect(payload.source).toBe('n1')
    expect(payload.target).toBe('n2')

    inst.callbacks.onLinkHover(null, link)
    expect(wrapper.emitted('hover-edge')!.at(-1)![0]).toBeNull()
  })

  it('emits select-edge when onLinkClick fires', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'organization', importance_score: 0.5, activity_score: 0 },
        { id: 'n2', label: 'B', type: 'person', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.5 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const link = inst.graphDataValue.links[0]
    inst.callbacks.onLinkClick(link, { detail: 1 } as unknown as MouseEvent)

    const emitted = wrapper.emitted('select-edge')
    expect(emitted).toBeTruthy()
    expect((emitted![0][0] as { relation_type: string }).relation_type).toBe('friend')
  })

  it('reconfigures forces and reheats when the physics prop changes', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'person', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [],
      physics: { chargeStrength: -220 },
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const forceCallsBefore = inst.d3ForceCalls
    const reheatBefore = inst.reheatCalls

    await wrapper.setProps({ physics: { chargeStrength: -500 } })
    await flushPromises()

    expect(inst.d3ForceCalls).toBeGreaterThan(forceCallsBefore)
    expect(inst.reheatCalls).toBeGreaterThan(reheatBefore)
  })

  it('calls _destructor on unmount', async () => {
    const wrapper = await mountComponent({
      nodes: [{ id: 'n1', label: 'A', type: 'person', importance_score: 0.5, activity_score: 0 }],
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    expect(inst.destructorCalled).toBe(false)
    wrapper.unmount()
    expect(inst.destructorCalled).toBe(true)
  })
})
