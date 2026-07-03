import { getStanceColor } from '../constants/stances'

export interface NodeProp {
  id: string
  label: string
  type: string
  importance_score: number
  activity_score: number
  stance?: string
  status?: string
  tier?: string
}

export interface EdgeProp {
  id?: string
  source: string
  target: string
  relation_type: string
  weight: number
  label?: string
}

export interface SimNode extends NodeProp {
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number
  fy?: number
  index?: number
}

export interface SimLink {
  id?: string
  source: string | SimNode
  target: string | SimNode
  relation_type: string
  weight: number
  label?: string
  synthetic?: boolean
  curvature?: number
}

export const TYPE_COLORS: Record<string, string> = {
  organization: '#4FC3F7',
  person: '#FFB74D',
  policy: '#81C784',
  market: '#E57373',
  technology: '#BA68C8',
  resource: '#4DB6AC',
  concept: '#64B5F6',
  risk: '#FF8A65',
  opportunity: '#AED581',
  agent: '#FFB74D',
  friend: '#4FC3F7',
  family: '#FFB74D',
  colleague: '#81C784',
  neighbor: '#4DB6AC',
  acquaintance: '#90A4AE',
  mentions: '#BA68C8',
  default: '#90A4AE',
}

const NODE_PROP_KEYS = [
  'id',
  'label',
  'type',
  'importance_score',
  'activity_score',
  'stance',
  'status',
  'tier',
] as const

const EDGE_PROP_KEYS = ['id', 'source', 'target', 'relation_type', 'weight', 'label'] as const
const MIN_LINKS_PER_NODE_FOR_CONNECTED_VIEW = 1.25
const MAX_SYNTHETIC_NEIGHBORS = 3

export function clamp01(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value)) return 0
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

export function nodeColor(type: string | undefined): string {
  if (!type) return TYPE_COLORS.default
  return TYPE_COLORS[type] ?? TYPE_COLORS.default
}

export function nodeDisplayColor(node: Pick<NodeProp, 'type' | 'stance'>): string {
  const typeColor = nodeColor(node.type)
  if (node.type === 'agent' && node.stance) {
    return getStanceColor(node.stance, typeColor)
  }
  return typeColor
}

export const POPULATION_NODE_RADIUS = 2.2

export function nodeRadius(
  node: Pick<NodeProp, 'importance_score' | 'activity_score' | 'status' | 'tier'>,
  degree = 0,
): number {
  if (node.tier === 'population') return POPULATION_NODE_RADIUS
  const importance = clamp01(node.importance_score ?? 0.4)
  const activityBoost = (node.activity_score ?? 0) > 0 || node.status === 'speaking' ? 3 : 0
  const degreeBoost = Math.min(8, Math.sqrt(Math.max(0, degree)) * 0.9)
  return 5 + importance * 8 + activityBoost + degreeBoost
}

export function computeDegrees(edges: ReadonlyArray<EdgeProp | SimLink>): Map<string, number> {
  const degrees = new Map<string, number>()
  for (const [id, neighbors] of buildAdjacency(edges)) {
    degrees.set(id, neighbors.size)
  }
  return degrees
}

export function labelAlpha(globalScale: number): number {
  const FADE_START = 0.45
  const FADE_END = 0.9
  if (globalScale <= FADE_START) return 0
  if (globalScale >= FADE_END) return 1
  return (globalScale - FADE_START) / (FADE_END - FADE_START)
}

export function linkWidth(weight: number | null | undefined): number {
  return 0.7 + clamp01(weight) * 2.4
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const trimmed = hex.replace('#', '')
  const full = trimmed.length === 3
    ? trimmed.split('').map((c) => c + c).join('')
    : trimmed
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return {
    r: Number.isNaN(r) ? 144 : r,
    g: Number.isNaN(g) ? 164 : g,
    b: Number.isNaN(b) ? 174 : b,
  }
}

export function withAlpha(color: string, alpha: number): string {
  const a = clamp01(alpha)
  const { r, g, b } = hexToRgb(color)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

export function linkColor(relation_type: string, weight: number | null | undefined, dimmed: boolean): string {
  const base = nodeColor(relation_type)
  const alpha = dimmed ? 0.06 : Math.min(0.42, 0.14 + clamp01(weight) * 0.28)
  return withAlpha(base, alpha)
}

export interface GraphPhysics {
  chargeStrength: number
  linkDistance: number
  centerStrength: number
  collidePadding: number
}

export const DEFAULT_PHYSICS: GraphPhysics = {
  chargeStrength: -220,
  linkDistance: 60,
  centerStrength: 0.04,
  collidePadding: 4,
}

export function syntheticLinkColor(sourceColor: string, targetColor: string, dimmed: boolean): string {
  if (dimmed) return 'rgba(148, 163, 184, 0.12)'
  const source = hexToRgb(sourceColor)
  const target = hexToRgb(targetColor)
  const r = Math.round(source.r * 0.52 + target.r * 0.48)
  const g = Math.round(source.g * 0.52 + target.g * 0.48)
  const b = Math.round(source.b * 0.52 + target.b * 0.48)
  return `rgba(${r}, ${g}, ${b}, 0.32)`
}

function stableNodeSortKey(node: Pick<NodeProp, 'id' | 'stance' | 'type'>): string {
  return `${node.stance || node.type || ''}:${node.id}`
}

export function buildSyntheticLinks(
  nodes: ReadonlyArray<NodeProp>,
  edges: ReadonlyArray<EdgeProp>,
): SimLink[] {
  if (nodes.length < 3) return []
  if (edges.length >= nodes.length * MIN_LINKS_PER_NODE_FOR_CONNECTED_VIEW) return []

  const realPairs = new Set<string>()
  const degree = new Map(nodes.map((node) => [node.id, 0]))
  const pairKey = (a: string, b: string) => [a, b].sort().join('::')

  for (const edge of edges) {
    const source = endpointId(edge.source)
    const target = endpointId(edge.target)
    if (!source || !target || source === target) continue
    realPairs.add(pairKey(source, target))
    degree.set(source, (degree.get(source) ?? 0) + 1)
    degree.set(target, (degree.get(target) ?? 0) + 1)
  }

  const ordered = [...nodes].sort((a, b) => stableNodeSortKey(a).localeCompare(stableNodeSortKey(b)))
  const synthetic: SimLink[] = []
  const syntheticPairs = new Set<string>()
  const targetNeighborCount = Math.min(MAX_SYNTHETIC_NEIGHBORS, Math.max(1, Math.ceil(nodes.length / 28)))
  const addSynthetic = (source: NodeProp, target: NodeProp, weight: number) => {
    if (source.id === target.id) return
    const key = pairKey(source.id, target.id)
    if (realPairs.has(key) || syntheticPairs.has(key)) return
    syntheticPairs.add(key)
    synthetic.push({
      id: `synthetic:${key}`,
      source: source.id,
      target: target.id,
      relation_type: 'visual_affinity',
      weight,
      synthetic: true,
    })
  }

  for (let i = 0; i < ordered.length; i++) {
    const source = ordered[i]
    const sourceDegree = degree.get(source.id) ?? 0
    const neighbors = sourceDegree === 0 ? targetNeighborCount + 1 : targetNeighborCount
    for (let offset = 1; offset <= neighbors; offset++) {
      let targetIndex = (i + offset * 7) % ordered.length
      if (targetIndex === i) targetIndex = (i + offset) % ordered.length
      const target = ordered[targetIndex]
      addSynthetic(source, target, Math.max(0.18, 0.42 - offset * 0.06))
    }
  }

  return synthetic
}

function endpointId(end: string | { id?: string | number } | undefined): string {
  if (end == null) return ''
  if (typeof end === 'string') return end
  if (typeof end === 'number') return String(end)
  return String(end.id ?? '')
}

export function assignLinkCurvatures(links: SimLink[]): void {
  const groups = new Map<string, SimLink[]>()
  for (const link of links) {
    if (link.synthetic) continue
    // Clear any prior value so a reused link that dropped from a parallel pair
    // back to a lone edge doesn't keep its stale curvature.
    link.curvature = undefined
    const source = endpointId(link.source as string | { id?: string | number })
    const target = endpointId(link.target as string | { id?: string | number })
    const key = [source, target].sort().join('::')
    const group = groups.get(key)
    if (group) group.push(link)
    else groups.set(key, [link])
  }

  for (const group of groups.values()) {
    const total = group.length
    if (total < 2) continue
    const range = Math.min(0.6, 0.3 + total * 0.08)
    group.forEach((link, index) => {
      const base = (index / (total - 1) - 0.5) * range
      const source = endpointId(link.source as string | { id?: string | number })
      const target = endpointId(link.target as string | { id?: string | number })
      // Normalize against the sorted pair key so anti-parallel edges land on
      // opposite physical sides in force-graph's source->target frame.
      link.curvature = source > target ? -base : base
    })
  }
}

export function buildAdjacency(edges: ReadonlyArray<EdgeProp | SimLink>): Map<string, Set<string>> {
  const map = new Map<string, Set<string>>()
  for (const edge of edges) {
    const source = endpointId(edge.source as string | { id?: string | number })
    const target = endpointId(edge.target as string | { id?: string | number })
    if (!source || !target) continue
    if (!map.has(source)) map.set(source, new Set())
    if (!map.has(target)) map.set(target, new Set())
    map.get(source)!.add(target)
    map.get(target)!.add(source)
  }
  return map
}

export interface MergeGraphDataCache {
  populationNodeProps: NodeProp[]
  populationNodes: SimNode[]
  populationEdgeProps: EdgeProp[]
  populationLinks: SimLink[]
}

export function createMergeGraphDataCache(): MergeGraphDataCache {
  return {
    populationNodeProps: [],
    populationNodes: [],
    populationEdgeProps: [],
    populationLinks: [],
  }
}

function findPopulationRange<T>(items: ReadonlyArray<T>, predicate: (item: T) => boolean): { start: number; end: number } | null {
  let start = -1
  let end = -1
  for (let i = 0; i < items.length; i++) {
    if (predicate(items[i])) {
      if (start === -1) start = i
      end = i + 1
    } else if (start !== -1) {
      break
    }
  }
  return start === -1 ? null : { start, end }
}

function segmentMatches<T>(items: ReadonlyArray<T>, range: { start: number; end: number }, cached: ReadonlyArray<T>): boolean {
  if (range.end - range.start !== cached.length) return false
  for (let i = 0; i < cached.length; i++) {
    if (items[range.start + i] !== cached[i]) return false
  }
  return true
}

function updateSimNode(existing: SimNode | undefined, next: NodeProp): SimNode {
  if (existing) {
    // Mutate in place so force-graph keeps the same object reference,
    // preserving x/y/vx/vy/fx/fy/index across reactive updates.
    existing.label = next.label
    existing.type = next.type
    existing.importance_score = next.importance_score
    existing.activity_score = next.activity_score
    existing.stance = next.stance
    existing.status = next.status
    existing.tier = next.tier
    return existing
  }
  return { ...next }
}

function toSimLink(edge: EdgeProp): SimLink {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    relation_type: edge.relation_type,
    weight: edge.weight,
    label: edge.label,
  }
}

export function mergeGraphData(
  prevNodes: ReadonlyArray<SimNode>,
  newNodes: ReadonlyArray<NodeProp>,
  newEdges: ReadonlyArray<EdgeProp>,
  cache?: MergeGraphDataCache,
): { nodes: SimNode[]; links: SimLink[] } {
  const prevById = new Map(prevNodes.map((n) => [n.id, n]))
  const populationNodeRange = findPopulationRange(newNodes, (node) => node.tier === 'population')
  const canReusePopulationNodes = !!cache
    && !!populationNodeRange
    && segmentMatches(newNodes, populationNodeRange, cache.populationNodeProps)

  const nodes: SimNode[] = []
  for (let i = 0; i < newNodes.length; i++) {
    if (canReusePopulationNodes && populationNodeRange && i === populationNodeRange.start) {
      nodes.push(...cache!.populationNodes)
      i = populationNodeRange.end - 1
      continue
    }
    nodes.push(updateSimNode(prevById.get(newNodes[i].id), newNodes[i]))
  }
  if (cache && populationNodeRange && !canReusePopulationNodes) {
    cache.populationNodeProps = newNodes.slice(populationNodeRange.start, populationNodeRange.end)
    cache.populationNodes = nodes.slice(populationNodeRange.start, populationNodeRange.end)
  } else if (cache && !populationNodeRange) {
    cache.populationNodeProps = []
    cache.populationNodes = []
  }

  const nodeIds = new Set(nodes.map((n) => n.id))
  const populationEdgeRange = findPopulationRange(newEdges, (edge) => edge.id?.startsWith('pop-edge-') ?? false)
  const canReusePopulationLinks = !!cache
    && !!populationEdgeRange
    && segmentMatches(newEdges, populationEdgeRange, cache.populationEdgeProps)

  const validEdges: EdgeProp[] = []
  const links: SimLink[] = []
  for (let i = 0; i < newEdges.length; i++) {
    if (canReusePopulationLinks && populationEdgeRange && i === populationEdgeRange.start) {
      validEdges.push(...cache!.populationEdgeProps)
      links.push(...cache!.populationLinks)
      i = populationEdgeRange.end - 1
      continue
    }
    const edge = newEdges[i]
    if (!nodeIds.has(endpointId(edge.source)) || !nodeIds.has(endpointId(edge.target))) continue
    validEdges.push(edge)
    links.push(toSimLink(edge))
  }
  if (cache && populationEdgeRange && !canReusePopulationLinks) {
    const populationEdges = validEdges.filter((edge) => edge.id?.startsWith('pop-edge-'))
    cache.populationEdgeProps = populationEdges
    cache.populationLinks = links.filter((link) => link.id?.startsWith('pop-edge-'))
  } else if (cache && !populationEdgeRange) {
    cache.populationEdgeProps = []
    cache.populationLinks = []
  }

  assignLinkCurvatures(links)
  return { nodes, links: [...links, ...buildSyntheticLinks(nodes, validEdges)] }
}

export function toNodeProp(node: SimNode | NodeProp | null | undefined): NodeProp | null {
  if (!node) return null
  const source = node as unknown as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const key of NODE_PROP_KEYS) {
    if (key in source) out[key] = source[key]
  }
  return out as unknown as NodeProp
}

export function toEdgeProp(link: SimLink | EdgeProp | null | undefined): EdgeProp | null {
  if (!link) return null
  const source = link as unknown as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const key of EDGE_PROP_KEYS) {
    if (key === 'source' || key === 'target') {
      out[key] = endpointId(source[key] as string | { id?: string | number })
    } else if (key in source) {
      out[key] = source[key]
    }
  }
  return out as unknown as EdgeProp
}
