import { describe, expect, it } from 'vitest'

import {
  DEFAULT_PHYSICS,
  POPULATION_NODE_RADIUS,
  TYPE_COLORS,
  assignLinkCurvatures,
  buildAdjacency,
  buildSyntheticLinks,
  clamp01,
  computeDegrees,
  createMergeGraphDataCache,
  hashUnit,
  labelAlpha,
  linkColor,
  linkWidth,
  mergeGraphData,
  nodeColor,
  nodeDisplayColor,
  nodeRadius,
  syntheticLinkColor,
  toEdgeProp,
  toNodeProp,
  withAlpha,
  type EdgeProp,
  type NodeProp,
  type SimLink,
  type SimNode,
} from '../forceGraphHelpers'

const baseNode = (overrides: Partial<NodeProp> = {}): NodeProp => ({
  id: 'n',
  label: 'N',
  type: 'organization',
  importance_score: 0.5,
  activity_score: 0,
  ...overrides,
})

describe('clamp01', () => {
  it('clamps values into [0,1]', () => {
    expect(clamp01(-0.5)).toBe(0)
    expect(clamp01(0)).toBe(0)
    expect(clamp01(0.5)).toBe(0.5)
    expect(clamp01(1)).toBe(1)
    expect(clamp01(2)).toBe(1)
  })

  it('treats nullish and NaN as 0', () => {
    expect(clamp01(null)).toBe(0)
    expect(clamp01(undefined)).toBe(0)
    expect(clamp01(Number.NaN)).toBe(0)
  })
})

describe('nodeColor', () => {
  it('maps known types', () => {
    expect(nodeColor('organization')).toBe(TYPE_COLORS.organization)
    expect(nodeColor('person')).toBe(TYPE_COLORS.person)
  })

  it('falls back to default for unknown or empty', () => {
    expect(nodeColor('unknown_type')).toBe(TYPE_COLORS.default)
    expect(nodeColor(undefined)).toBe(TYPE_COLORS.default)
  })
})

describe('nodeDisplayColor', () => {
  it('uses stance color for society agent nodes', () => {
    expect(nodeDisplayColor(baseNode({ type: 'agent', stance: '反対' }))).toBe('#ef4444')
    expect(nodeDisplayColor(baseNode({ type: 'agent', stance: '賛成' }))).toBe('#22c55e')
  })

  it('keeps type color for non-agent nodes and unknown agent stances', () => {
    expect(nodeDisplayColor(baseNode({ type: 'organization', stance: '反対' }))).toBe(TYPE_COLORS.organization)
    expect(nodeDisplayColor(baseNode({ type: 'agent', stance: '不明' }))).toBe(TYPE_COLORS.agent)
  })
})

describe('nodeRadius', () => {
  it('scales with importance_score', () => {
    expect(nodeRadius({ importance_score: 0, activity_score: 0 })).toBe(5)
    expect(nodeRadius({ importance_score: 1, activity_score: 0 })).toBe(13)
  })

  it('adds activity boost when activity_score > 0', () => {
    expect(nodeRadius({ importance_score: 0.5, activity_score: 0.6 })).toBe(5 + 4 + 3)
  })

  it('adds activity boost when status is speaking', () => {
    expect(nodeRadius({ importance_score: 0.5, activity_score: 0, status: 'speaking' })).toBe(5 + 4 + 3)
  })

  it('handles nullish importance_score by defaulting to 0.4', () => {
    expect(nodeRadius({ importance_score: undefined as unknown as number, activity_score: 0 })).toBeCloseTo(5 + 0.4 * 8)
  })
})

describe('linkWidth', () => {
  it('floor at 0.7 and grows quietly with weight', () => {
    expect(linkWidth(0)).toBe(0.7)
    expect(linkWidth(1)).toBeCloseTo(3.1, 5)
    expect(linkWidth(undefined)).toBe(0.7)
  })
})

describe('linkColor', () => {
  it('uses relation_type color and reduces alpha when dimmed', () => {
    const normal = linkColor('friend', 0.5, false)
    const dimmed = linkColor('friend', 0.5, true)
    expect(normal).toMatch(/^rgba\(/)
    expect(dimmed).toContain('0.06')
    // normal should have higher alpha than dimmed
    const normalAlpha = Number(normal.match(/, (0\.\d+)\)/)?.[1])
    expect(normalAlpha).toBeGreaterThan(0.06)
  })

  it('keeps a quiet Obsidian-like alpha band [0.14, 0.42] for any weight', () => {
    const lo = linkColor('friend', 0, false)
    const hi = linkColor('friend', 1, false)
    expect(lo).toContain('0.14')
    const hiAlpha = Number(hi.match(/, (0\.\d+)\)/)?.[1])
    expect(hiAlpha).toBeGreaterThan(0.3)
    expect(hiAlpha).toBeLessThanOrEqual(0.42)
  })
})

describe('syntheticLinkColor', () => {
  it('collapses endpoint colors toward a quiet cool slate at a hair of alpha', () => {
    // Opposed stance colors (green vs red) must NOT survive as loud yarn — the
    // result is dominated by slate with only a trace of the endpoints.
    expect(syntheticLinkColor('#22c55e', '#ef4444', false)).toBe('rgba(122, 137, 152, 0.1)')
    expect(syntheticLinkColor('#22c55e', '#ef4444', true)).toBe('rgba(120, 138, 168, 0.04)')
  })

  it('keeps synthetic links far quieter than real relation links', () => {
    const synthAlpha = Number(syntheticLinkColor('#5aa0c8', '#6faa8f', false).match(/, (0\.\d+)\)/)?.[1])
    const realAlpha = Number(linkColor('friend', 1, false).match(/, (0\.\d+)\)/)?.[1])
    expect(synthAlpha).toBeLessThan(realAlpha)
  })
})

describe('hashUnit', () => {
  it('is deterministic and bounded in [0, 1)', () => {
    for (const id of ['agent-0', 'agent-9999', 'kg-entity-abc', '']) {
      const a = hashUnit(id)
      const b = hashUnit(id)
      expect(a).toBe(b)
      expect(a).toBeGreaterThanOrEqual(0)
      expect(a).toBeLessThan(1)
    }
  })

  it('spreads distinct ids across the range (no trivial collisions)', () => {
    const values = new Set(Array.from({ length: 500 }, (_, i) => hashUnit(`agent-${i}`)))
    // A decent hash keeps almost all 500 ids distinct.
    expect(values.size).toBeGreaterThan(480)
  })
})

describe('withAlpha', () => {
  it('converts hex to rgba', () => {
    expect(withAlpha('#4FC3F7', 0.5)).toBe('rgba(79, 195, 247, 0.5)')
  })

  it('handles short hex', () => {
    expect(withAlpha('#abc', 1)).toBe('rgba(170, 187, 204, 1)')
  })

  it('clamps alpha', () => {
    expect(withAlpha('#000000', 2)).toContain(', 1)')
    expect(withAlpha('#000000', -1)).toContain(', 0)')
  })
})

describe('buildAdjacency', () => {
  it('builds bidirectional sets from string endpoints', () => {
    const edges: EdgeProp[] = [
      { source: 'a', target: 'b', relation_type: 'friend', weight: 0.5 },
      { source: 'b', target: 'c', relation_type: 'friend', weight: 0.3 },
    ]
    const adj = buildAdjacency(edges)
    expect(adj.get('a')?.has('b')).toBe(true)
    expect(adj.get('b')?.has('a')).toBe(true)
    expect(adj.get('b')?.has('c')).toBe(true)
    expect(adj.get('c')?.has('b')).toBe(true)
    expect(adj.get('a')?.has('c')).toBe(false)
  })

  it('handles object endpoints (force-graph injected)', () => {
    const edges = [
      { source: { id: 'a' }, target: { id: 'b' }, relation_type: 'friend', weight: 0.5 },
    ] as unknown as EdgeProp[]
    const adj = buildAdjacency(edges)
    expect(adj.get('a')?.has('b')).toBe(true)
  })
})

describe('computeDegrees', () => {
  it('counts distinct neighbors per node', () => {
    const edges: EdgeProp[] = [
      { source: 'a', target: 'b', relation_type: 'friend', weight: 0.5 },
      { source: 'a', target: 'c', relation_type: 'friend', weight: 0.5 },
      { source: 'b', target: 'c', relation_type: 'friend', weight: 0.5 },
    ]
    const degrees = computeDegrees(edges)
    expect(degrees.get('a')).toBe(2)
    expect(degrees.get('b')).toBe(2)
    expect(degrees.get('c')).toBe(2)
  })

  it('handles hub topology and missing nodes', () => {
    const edges: EdgeProp[] = [
      { source: 'hub', target: 'l1', relation_type: 'friend', weight: 1 },
      { source: 'hub', target: 'l2', relation_type: 'friend', weight: 1 },
      { source: 'hub', target: 'l3', relation_type: 'friend', weight: 1 },
    ]
    const degrees = computeDegrees(edges)
    expect(degrees.get('hub')).toBe(3)
    expect(degrees.get('l1')).toBe(1)
    expect(degrees.get('unknown')).toBeUndefined()
  })

  it('returns empty map for no edges', () => {
    expect(computeDegrees([]).size).toBe(0)
  })
})

describe('nodeRadius with degree', () => {
  it('keeps backward-compatible values when degree omitted', () => {
    expect(nodeRadius({ importance_score: 0, activity_score: 0 })).toBe(5)
    expect(nodeRadius({ importance_score: 1, activity_score: 0 })).toBe(13)
  })

  it('grows with degree using sqrt scaling for Obsidian-like hubs', () => {
    const base = nodeRadius({ importance_score: 0.5, activity_score: 0 }, 0)
    const d4 = nodeRadius({ importance_score: 0.5, activity_score: 0 }, 4)
    const d16 = nodeRadius({ importance_score: 0.5, activity_score: 0 }, 16)
    expect(d4).toBeGreaterThan(base)
    expect(d16).toBeGreaterThan(d4)
    expect(d16 - base).toBeCloseTo((d4 - base) * 2, 5)
  })

  it('caps degree boost so giant hubs do not dominate', () => {
    const d100 = nodeRadius({ importance_score: 0.5, activity_score: 0 }, 100)
    const d10000 = nodeRadius({ importance_score: 0.5, activity_score: 0 }, 10000)
    expect(d10000 - d100).toBeLessThanOrEqual(8)
  })
})

describe('nodeRadius for population tier', () => {
  it('uses a fixed tiny dot for population tier regardless of activity or degree', () => {
    const r = nodeRadius({ importance_score: 0.9, activity_score: 1, tier: 'population' }, 50)
    expect(r).toBe(POPULATION_NODE_RADIUS)
    expect(r).toBeLessThan(3)
  })

  it('keeps ordinary nodes on the existing radius scale', () => {
    expect(nodeRadius({ importance_score: 0, activity_score: 0 })).toBe(5)
  })
})

describe('labelAlpha', () => {
  it('hides labels across the whole overview zoom (fit lands ~1x)', () => {
    expect(labelAlpha(0.2)).toBe(0)
    expect(labelAlpha(1)).toBe(0)
    expect(labelAlpha(2)).toBe(0)
  })

  it('fades in continuously between 2.0 and 3.4 (deliberate zoom-in)', () => {
    const mid = labelAlpha(2.7)
    expect(mid).toBeGreaterThan(0)
    expect(mid).toBeLessThan(1)
    expect(labelAlpha(2.2)).toBeLessThan(labelAlpha(3.2))
  })

  it('is fully visible only once zoomed deep in', () => {
    expect(labelAlpha(3.4)).toBe(1)
    expect(labelAlpha(6)).toBe(1)
  })
})

describe('DEFAULT_PHYSICS', () => {
  it('matches the Obsidian-style baseline force settings', () => {
    expect(DEFAULT_PHYSICS).toEqual({
      chargeStrength: -220,
      linkDistance: 60,
      centerStrength: 0.04,
      collidePadding: 4,
    })
  })
})

describe('buildSyntheticLinks', () => {
  it('adds visual affinity links for sparse completed graphs', () => {
    const nodes = Array.from({ length: 8 }, (_, i) => baseNode({
      id: `agent-${i + 1}`,
      type: 'agent',
      stance: i % 2 === 0 ? '賛成' : '反対',
    }))

    const links = buildSyntheticLinks(nodes, [])

    expect(links.length).toBeGreaterThan(nodes.length)
    expect(links.every((link) => link.synthetic)).toBe(true)
    expect(links.every((link) => link.relation_type === 'visual_affinity')).toBe(true)
    expect(links.every((link) => link.source !== link.target)).toBe(true)
  })

  it('does not add visual links when real graph density is already sufficient', () => {
    const nodes = Array.from({ length: 4 }, (_, i) => baseNode({ id: `n${i}` }))
    const edges: EdgeProp[] = [
      { source: 'n0', target: 'n1', relation_type: 'friend', weight: 0.5 },
      { source: 'n1', target: 'n2', relation_type: 'friend', weight: 0.5 },
      { source: 'n2', target: 'n3', relation_type: 'friend', weight: 0.5 },
      { source: 'n3', target: 'n0', relation_type: 'friend', weight: 0.5 },
      { source: 'n0', target: 'n2', relation_type: 'friend', weight: 0.5 },
    ]

    expect(buildSyntheticLinks(nodes, edges)).toEqual([])
  })
})

describe('assignLinkCurvatures', () => {
  const simLink = (source: string, target: string, overrides: Partial<SimLink> = {}): SimLink => ({
    source,
    target,
    relation_type: 'friend',
    weight: 0.5,
    ...overrides,
  })

  it('leaves a lone edge between a pair without curvature', () => {
    const links = [simLink('a', 'b')]
    assignLinkCurvatures(links)
    expect(links[0].curvature).toBeUndefined()
  })

  it('splits two parallel edges into symmetric opposite curvatures', () => {
    const links = [
      simLink('a', 'b', { relation_type: 'friend' }),
      simLink('a', 'b', { relation_type: 'colleague' }),
    ]
    assignLinkCurvatures(links)
    const [c0, c1] = links.map((l) => l.curvature ?? Number.NaN)
    expect(c0).not.toBe(0)
    expect(c0 + c1).toBeCloseTo(0, 6)
    expect(Math.abs(c0)).toBeCloseTo(Math.abs(c1), 6)
  })

  it('keeps the middle of three parallel edges straight with symmetric ends', () => {
    const links = [simLink('a', 'b'), simLink('a', 'b'), simLink('a', 'b')]
    assignLinkCurvatures(links)
    const [c0, c1, c2] = links.map((l) => l.curvature ?? Number.NaN)
    expect(c1).toBeCloseTo(0, 6)
    expect(c0).not.toBe(0)
    expect(c0).toBeCloseTo(-c2, 6)
  })

  it('normalizes reversed edges so anti-parallel links curve to the same slot', () => {
    // Same pair, opposite directions. The reversed edge flips sign so both
    // resolve to matching curvature in force-graph's source->target frame,
    // which renders them on opposite physical sides (no overlap).
    const forward = simLink('a', 'b')
    const reverse = simLink('b', 'a')
    assignLinkCurvatures([forward, reverse])
    expect(forward.curvature).not.toBe(0)
    expect(forward.curvature).toBeCloseTo(reverse.curvature ?? Number.NaN, 6)
  })

  it('skips synthetic links entirely', () => {
    const links = [
      simLink('a', 'b', { synthetic: true }),
      simLink('a', 'b', { synthetic: true }),
    ]
    assignLinkCurvatures(links)
    expect(links.every((l) => l.curvature === undefined)).toBe(true)
  })

  it('clears stale curvature when a reused link drops back to a single edge', () => {
    const solo = simLink('a', 'b', { relation_type: 'friend' })
    const sibling = simLink('a', 'b', { relation_type: 'colleague' })
    assignLinkCurvatures([solo, sibling])
    expect(solo.curvature).not.toBeUndefined()

    // Reuse the same `solo` object after its parallel sibling is gone.
    assignLinkCurvatures([solo])
    expect(solo.curvature).toBeUndefined()
  })
})

describe('mergeGraphData', () => {
  it('preserves x/y/vx/vy/fx/fy on existing nodes by mutating same reference', () => {
    const prev: SimNode[] = [
      {
        id: 'a', label: 'A old', type: 'organization', importance_score: 0.3, activity_score: 0,
        x: 100, y: 200, vx: 1, vy: 2, fx: 50, fy: 60,
      },
    ]
    const result = mergeGraphData(
      prev,
      [baseNode({ id: 'a', label: 'A new', importance_score: 0.9 })],
      [],
    )
    expect(result.nodes).toHaveLength(1)
    const merged = result.nodes[0]
    expect(merged).toBe(prev[0]) // same reference — critical for force-graph stability
    expect(merged.x).toBe(100)
    expect(merged.y).toBe(200)
    expect(merged.vx).toBe(1)
    expect(merged.vy).toBe(2)
    expect(merged.fx).toBe(50)
    expect(merged.fy).toBe(60)
    expect(merged.label).toBe('A new')
    expect(merged.importance_score).toBe(0.9)
  })

  it('updates tier on existing node references', () => {
    const prev: SimNode[] = [{ ...baseNode({ id: 'a' }), tier: 'population', x: 100 }]
    const result = mergeGraphData(
      prev,
      [baseNode({ id: 'a', tier: undefined })],
      [],
    )
    expect(result.nodes[0]).toBe(prev[0])
    expect(result.nodes[0].tier).toBeUndefined()
    expect(result.nodes[0].x).toBe(100)
  })

  it('adds brand-new nodes without position', () => {
    const result = mergeGraphData([], [baseNode({ id: 'b' })], [])
    expect(result.nodes).toHaveLength(1)
    expect(result.nodes[0].x).toBeUndefined()
  })

  it('drops nodes that disappear from new set', () => {
    const prev: SimNode[] = [{ ...baseNode({ id: 'gone' }), x: 1, y: 2 }]
    const result = mergeGraphData(prev, [baseNode({ id: 'kept' })], [])
    expect(result.nodes.map((n) => n.id)).toEqual(['kept'])
  })

  it('passes edges through as plain link objects', () => {
    const result = mergeGraphData(
      [],
      [baseNode({ id: 'a' }), baseNode({ id: 'b' })],
      [{ source: 'a', target: 'b', relation_type: 'friend', weight: 0.6 }],
    )
    expect(result.links).toHaveLength(1)
    expect(result.links[0].source).toBe('a')
    expect(result.links[0].target).toBe('b')
    expect(result.links[0].weight).toBe(0.6)
  })

  it('includes synthetic visual links when persisted graph edges are too sparse', () => {
    const nodes = Array.from({ length: 6 }, (_, i) => baseNode({ id: `agent-${i + 1}` }))
    const result = mergeGraphData([], nodes, [])

    expect(result.links.some((link) => link.synthetic)).toBe(true)
  })

  it('applies curvature distribution to parallel real edges', () => {
    const result = mergeGraphData(
      [],
      [baseNode({ id: 'a' }), baseNode({ id: 'b' })],
      [
        { source: 'a', target: 'b', relation_type: 'friend', weight: 0.5 },
        { source: 'a', target: 'b', relation_type: 'colleague', weight: 0.5 },
      ],
    )
    const real = result.links.filter((link) => !link.synthetic)
    expect(real).toHaveLength(2)
    const [c0, c1] = real.map((link) => link.curvature ?? Number.NaN)
    expect(c0).not.toBe(0)
    expect(c0 + c1).toBeCloseTo(0, 6)
  })

  it('drops links whose endpoints are missing from the node set before synthetic links are built', () => {
    const nodes: NodeProp[] = [
      baseNode({ id: 'a' }),
      baseNode({ id: 'b' }),
    ]
    const edges: EdgeProp[] = [
      { source: 'a', target: 'b', relation_type: 'friend', weight: 0.5 },
      { source: 'a', target: 'ghost', relation_type: 'friend', weight: 0.9 },
      { source: 'ghost2', target: 'b', relation_type: 'friend', weight: 0.9 },
    ]
    const realLinks = mergeGraphData([], nodes, edges).links.filter((link) => !link.synthetic)
    expect(realLinks).toHaveLength(1)
    expect(realLinks[0]).toMatchObject({ source: 'a', target: 'b' })
  })

  it('keeps all real links when endpoints all exist', () => {
    const nodes: NodeProp[] = [baseNode({ id: 'a' }), baseNode({ id: 'b' }), baseNode({ id: 'c' })]
    const edges: EdgeProp[] = [
      { source: 'a', target: 'b', relation_type: 'friend', weight: 0.5 },
      { source: 'b', target: 'c', relation_type: 'family', weight: 0.5 },
    ]
    const realLinks = mergeGraphData([], nodes, edges).links.filter((link) => !link.synthetic)
    expect(realLinks).toHaveLength(2)
  })

  it('reuses cached population links when only non-population graph data changes', () => {
    const cache = createMergeGraphDataCache()
    const populationNodes = Array.from({ length: 100 }, (_, i) => baseNode({
      id: `pop-${i}`,
      label: '',
      type: 'agent',
      importance_score: 0.1,
      tier: 'population',
    }))
    const populationEdges: EdgeProp[] = Array.from({ length: 99 }, (_, i) => ({
      id: `pop-edge-${i}`,
      source: `pop-${i}`,
      target: `pop-${i + 1}`,
      relation_type: 'acquaintance',
      weight: 0.4,
    }))

    const first = mergeGraphData(
      [],
      [baseNode({ id: 'agent-1', label: 'before' }), ...populationNodes],
      [{ id: 'live-edge', source: 'agent-1', target: 'pop-0', relation_type: 'friend', weight: 0.5 }, ...populationEdges],
      cache,
    )
    const firstPopulationLink = first.links.find((link) => link.id === 'pop-edge-10')

    const second = mergeGraphData(
      first.nodes,
      [baseNode({ id: 'agent-1', label: 'after' }), ...populationNodes],
      [{ id: 'live-edge', source: 'agent-1', target: 'pop-1', relation_type: 'friend', weight: 0.9 }, ...populationEdges],
      cache,
    )

    expect(second.links.find((link) => link.id === 'pop-edge-10')).toBe(firstPopulationLink)
    expect(second.nodes.find((node) => node.id === 'pop-10')).toBe(first.nodes.find((node) => node.id === 'pop-10'))
  })
})

describe('toNodeProp', () => {
  it('strips force-graph injected fields (x/y/vx/vy/fx/fy/index)', () => {
    const sim: SimNode = {
      id: 'a', label: 'A', type: 'organization', importance_score: 0.5, activity_score: 0,
      x: 1, y: 2, vx: 3, vy: 4, fx: 5, fy: 6, index: 7,
    }
    const result = toNodeProp(sim) as unknown as Record<string, unknown>
    expect(result.x).toBeUndefined()
    expect(result.vx).toBeUndefined()
    expect(result.fx).toBeUndefined()
    expect(result.index).toBeUndefined()
    expect(result.id).toBe('a')
    expect(result.label).toBe('A')
  })

  it('includes tier in serializable node props', () => {
    const result = toNodeProp({ ...baseNode({ id: 'p', tier: 'population' }), x: 1 })
    expect(result?.tier).toBe('population')
  })

  it('returns null for null input', () => {
    expect(toNodeProp(null)).toBeNull()
  })
})

describe('toEdgeProp', () => {
  it('flattens object endpoints back to ids', () => {
    const link = {
      source: { id: 'a' },
      target: { id: 'b' },
      relation_type: 'friend',
      weight: 0.5,
    } as unknown as EdgeProp
    const result = toEdgeProp(link)
    expect(result?.source).toBe('a')
    expect(result?.target).toBe('b')
  })

  it('keeps string endpoints', () => {
    const result = toEdgeProp({ source: 'a', target: 'b', relation_type: 'friend', weight: 0.3 })
    expect(result?.source).toBe('a')
    expect(result?.target).toBe('b')
  })

  it('returns null for null input', () => {
    expect(toEdgeProp(null)).toBeNull()
  })
})
