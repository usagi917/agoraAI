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
        if (prop === 'd3ForceCalls') return self.d3ForceCalls
        if (prop === 'reheatCalls') return self.reheatCalls
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

  function createCanvasContext() {
    return {
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      stroke: vi.fn(),
      strokeText: vi.fn(),
      fillText: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      setTransform: vi.fn(),
      fillRect: vi.fn(),
      createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
      canvas: { width: 800, height: 600 },
      set fillStyle(_value: string) {},
      set strokeStyle(_value: string) {},
      set lineWidth(_value: number) {},
      set lineJoin(_value: string) {},
      set font(_value: string) {},
      set textAlign(_value: string) {},
      set textBaseline(_value: string) {},
      set globalCompositeOperation(_value: string) {},
    } as unknown as CanvasRenderingContext2D & {
      strokeText: ReturnType<typeof vi.fn>
      fillText: ReturnType<typeof vi.fn>
    }
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

  it('configures Obsidian-style canvas layers and quiet particle settings', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'organization', importance_score: 0.8, activity_score: 0 },
        { id: 'n2', label: 'Bob', type: 'person', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.8 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    expect(inst.setterCalls.backgroundColor?.[0]).toBe('#05060d')
    expect(inst.setterCalls.nodeCanvasObjectMode?.[0]).toBeTypeOf('function')
    expect(inst.setterCalls.linkCurvature?.[0]).toBeTypeOf('function')
    expect(inst.setterCalls.linkDirectionalParticleSpeed?.[0]).toBeTypeOf('function')
    expect(inst.setterCalls.linkDirectionalParticleWidth?.[0]).toBe(1.6)

    const link = inst.graphDataValue.links[0]
    expect((inst.setterCalls.linkDirectionalParticles?.[0] as (link: unknown) => number)(link)).toBe(1)
    expect((inst.setterCalls.linkCurvature?.[0] as (link: unknown) => number)(link)).toBeGreaterThan(0)
    void wrapper
  })

  it('renders population edges as a thin static mist', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'agent', importance_score: 0.8, activity_score: 0 },
        { id: 'n2', label: 'Bob', type: 'agent', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { id: 'pop-edge-1', source: 'n1', target: 'n2', relation_type: 'friend', weight: 1 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const link = inst.graphDataValue.links[0]
    expect((inst.setterCalls.linkWidth?.[0] as (link: unknown) => number)(link)).toBe(0.4)
    expect((inst.setterCalls.linkDirectionalParticles?.[0] as (link: unknown) => number)(link)).toBe(0)
    expect((inst.setterCalls.linkColor?.[0] as (link: unknown) => string)(link)).toContain('0.05')
    void wrapper
  })

  it('force-renders labels when the non-population graph is small even at far zoom', async () => {
    await mountComponent({
      nodes: [
        { id: 'n1', label: 'Alice', type: 'agent', importance_score: 0.5, activity_score: 0 },
        ...Array.from({ length: 50 }, (_, i) => ({
          id: `pop-${i}`,
          label: '',
          type: 'agent',
          importance_score: 0.1,
          activity_score: 0,
          tier: 'population',
        })),
      ],
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const paintNode = inst.setterCalls.nodeCanvasObject?.[0] as (node: unknown, ctx: CanvasRenderingContext2D, scale: number) => void
    const node = inst.graphDataValue.nodes.find((n) => (n as { id: string }).id === 'n1') as { x: number; y: number }
    node.x = 10
    node.y = 20
    const ctx = createCanvasContext()

    paintNode(node, ctx, 0.2)

    expect(ctx.fillText).toHaveBeenCalledWith('Alice', 10, expect.any(Number))
  })

  it('does not force labels for large non-population graphs without selection, hover, or hub degree', async () => {
    await mountComponent({
      nodes: Array.from({ length: 41 }, (_, i) => ({
        id: `agent-${i}`,
        label: `Agent ${i}`,
        type: 'agent',
        importance_score: 0.5,
        activity_score: 0,
      })),
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const paintNode = inst.setterCalls.nodeCanvasObject?.[0] as (node: unknown, ctx: CanvasRenderingContext2D, scale: number) => void
    const node = inst.graphDataValue.nodes[0] as { x: number; y: number }
    node.x = 10
    node.y = 20
    const ctx = createCanvasContext()

    paintNode(node, ctx, 0.2)

    expect(ctx.fillText).not.toHaveBeenCalled()
  })

  it('adds non-interactive visual links when persisted graph data is too sparse', async () => {
    const wrapper = await mountComponent({
      nodes: Array.from({ length: 6 }, (_, index) => ({
        id: `agent-${index + 1}`,
        label: `Agent ${index + 1}`,
        type: 'agent',
        stance: index % 2 === 0 ? '賛成' : '反対',
        importance_score: 0.5,
        activity_score: 0,
      })),
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const syntheticLink = inst.graphDataValue.links.find((link) => (link as { synthetic?: boolean }).synthetic)
    expect(syntheticLink).toBeTruthy()
    expect((inst.setterCalls.linkDirectionalParticles?.[0] as (link: unknown) => number)(syntheticLink)).toBe(0)
    expect((inst.setterCalls.linkWidth?.[0] as (link: unknown) => number)(syntheticLink)).toBeGreaterThan(0)

    inst.callbacks.onLinkClick(syntheticLink, { detail: 1 } as unknown as MouseEvent)
    expect(wrapper.emitted('select-edge')).toBeFalsy()

    inst.callbacks.onLinkHover(syntheticLink, null)
    expect(wrapper.emitted('hover-edge')?.at(-1)?.[0]).toBeNull()
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

  it('emits background-click when the graph background is clicked', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'person', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    inst.callbacks.onBackgroundClick({ detail: 1 } as unknown as MouseEvent)

    expect(wrapper.emitted('background-click')).toHaveLength(1)
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

  it('fires a synapse pulse on a matching real link and emits a particle', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'agent', importance_score: 0.5, activity_score: 0 },
        { id: 'n2', label: 'B', type: 'agent', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.6 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const firePulse = (wrapper.vm as unknown as { firePulse: (s: string, t: string) => boolean }).firePulse
    expect(firePulse('n1', 'n2')).toBe(true)
    const emitted = inst.setterCalls.emitParticle?.[0] as { relation_type: string } | undefined
    expect(emitted).toBeTruthy()
    expect(emitted!.relation_type).toBe('friend')
  })

  it('fires a pulse regardless of edge direction', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'agent', importance_score: 0.5, activity_score: 0 },
        { id: 'n2', label: 'B', type: 'agent', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.6 },
      ],
    })
    await flushPromises()

    const firePulse = (wrapper.vm as unknown as { firePulse: (s: string, t: string) => boolean }).firePulse
    expect(firePulse('n2', 'n1')).toBe(true)
  })

  it('returns false and emits no particle when no link matches', async () => {
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'agent', importance_score: 0.5, activity_score: 0 },
        { id: 'n2', label: 'B', type: 'agent', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.6 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    const firePulse = (wrapper.vm as unknown as { firePulse: (s: string, t: string) => boolean }).firePulse
    expect(firePulse('n1', 'ghost')).toBe(false)
    expect(inst.setterCalls.emitParticle).toBeUndefined()
  })

  it('keeps a pulse alive across link-array recreation and expires it after the window', async () => {
    const nowSpy = vi.spyOn(performance, 'now').mockReturnValue(1000)
    const wrapper = await mountComponent({
      nodes: [
        { id: 'n1', label: 'A', type: 'agent', importance_score: 0.5, activity_score: 0 },
        { id: 'n2', label: 'B', type: 'agent', importance_score: 0.5, activity_score: 0 },
      ],
      edges: [
        { id: 'e1', source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.6 },
      ],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    // The glow layer's mode accessor reports 'after' only for firing links.
    const modeFn = inst.setterCalls.linkCanvasObjectMode?.[0] as (l: unknown) => string | undefined
    expect(modeFn).toBeTypeOf('function')

    const firePulse = (wrapper.vm as unknown as { firePulse: (s: string, t: string) => boolean }).firePulse
    expect(firePulse('n1', 'n2')).toBe(true)
    expect(modeFn(inst.graphDataValue.links[0])).toBe('after')

    // mergeGraphData rebuilds the link array with brand-new objects on every
    // store update. With an object-reference key the pulse would vanish here.
    await wrapper.setProps({
      edges: [{ id: 'e1', source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.6 }],
    })
    await flushPromises()
    const recreated = inst.graphDataValue.links[0]
    nowSpy.mockReturnValue(1500) // still inside the 900ms window (expiry 1900)
    expect(modeFn(recreated)).toBe('after')

    // Past the window: the entry expires and is dropped from the map.
    nowSpy.mockReturnValue(2000)
    expect(modeFn(recreated)).toBeUndefined()
  })

  it('does not fire across synthetic-only links', async () => {
    const wrapper = await mountComponent({
      nodes: Array.from({ length: 6 }, (_, index) => ({
        id: `agent-${index + 1}`,
        label: `Agent ${index + 1}`,
        type: 'agent',
        stance: index % 2 === 0 ? '賛成' : '反対',
        importance_score: 0.5,
        activity_score: 0,
      })),
      edges: [],
    })
    await flushPromises()

    const inst = MockForceGraph.lastInstance!
    // Sanity: a synthetic link exists between these nodes, but firePulse ignores it.
    expect(inst.graphDataValue.links.some((link) => (link as { synthetic?: boolean }).synthetic)).toBe(true)
    const firePulse = (wrapper.vm as unknown as { firePulse: (s: string, t: string) => boolean }).firePulse
    expect(firePulse('agent-1', 'agent-2')).toBe(false)
    expect(inst.setterCalls.emitParticle).toBeUndefined()
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
