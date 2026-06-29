import { describe, expect, it } from 'vitest'

import {
  TYPE_COLORS,
  buildAdjacency,
  buildSyntheticLinks,
  clamp01,
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
  it('floor at 0.9 and grows with weight', () => {
    expect(linkWidth(0)).toBe(0.9)
    expect(linkWidth(1)).toBeCloseTo(3.7, 5)
    expect(linkWidth(undefined)).toBe(0.9)
  })
})

describe('linkColor', () => {
  it('uses relation_type color and reduces alpha when dimmed', () => {
    const normal = linkColor('friend', 0.5, false)
    const dimmed = linkColor('friend', 0.5, true)
    expect(normal).toMatch(/^rgba\(/)
    expect(dimmed).toContain('0.12')
    // normal should have higher alpha than dimmed
    const normalAlpha = Number(normal.match(/, (0\.\d+)\)/)?.[1])
    expect(normalAlpha).toBeGreaterThan(0.12)
  })

  it('keeps alpha within [0.32, 0.82] band for any weight', () => {
    const lo = linkColor('friend', 0, false)
    const hi = linkColor('friend', 1, false)
    expect(lo).toContain('0.32')
    const hiAlpha = Number(hi.match(/, (0\.\d+)\)/)?.[1])
    expect(hiAlpha).toBeGreaterThan(0.5)
    expect(hiAlpha).toBeLessThanOrEqual(0.82)
  })
})

describe('syntheticLinkColor', () => {
  it('mixes endpoint colors into a canvas-safe rgba string', () => {
    expect(syntheticLinkColor('#22c55e', '#ef4444', false)).toMatch(/^rgba\(\d+, \d+, \d+, 0\.32\)$/)
    expect(syntheticLinkColor('#22c55e', '#ef4444', true)).toBe('rgba(148, 163, 184, 0.12)')
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
