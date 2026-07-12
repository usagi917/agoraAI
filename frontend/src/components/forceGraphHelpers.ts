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
  spawnedAt?: number
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
  organization: '#aeb9e8', person: '#c3cdf2', policy: '#b0c4e4', market: '#c9c3ea',
  technology: '#b6b1ec', resource: '#a9c1e6', concept: '#bac6ee', risk: '#d4b9d4',
  opportunity: '#b5cbe0', agent: '#c3cdf2', friend: '#a9b8e6', family: '#c3bfe0',
  colleague: '#aec4e2', neighbor: '#a9c1e6', acquaintance: '#9aa6c8', mentions: '#b6b1ec',
  default: '#aab4d6',
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
const MAX_SYNTHETIC_NEIGHBORS = 7

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

export const PENDING_AGENT_COLOR = '#c3cdf2'

export function mixHex(a: string, b: string, t: number): string {
  const from = hexToRgb(a)
  const to = hexToRgb(b)
  const amount = clamp01(t)
  const channel = (start: number, end: number) => Math.round(start + (end - start) * amount)
  return `#${[channel(from.r, to.r), channel(from.g, to.g), channel(from.b, to.b)]
    .map((value) => value.toString(16).padStart(2, '0')).join('')}`
}

export function softenStanceColor(stance: string, fallback: string): string {
  return mixHex(getStanceColor(stance, fallback), '#c3cdf2', 0.45)
}

export function nodeDisplayColor(node: Pick<NodeProp, 'type' | 'stance'>): string {
  const typeColor = nodeColor(node.type)
  if (node.type === 'agent') {
    return node.stance ? softenStanceColor(node.stance, typeColor) : PENDING_AGENT_COLOR
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
  const activityBoost = (node.activity_score ?? 0) > 0 || node.status === 'speaking' ? 1 : 0
  const degreeBoost = Math.min(3.5, Math.sqrt(Math.max(0, degree)) * 0.6)
  return 1.6 + importance * 2 + activityBoost + degreeBoost
}

export function computeDegrees(edges: ReadonlyArray<EdgeProp | SimLink>): Map<string, number> {
  const degrees = new Map<string, number>()
  for (const [id, neighbors] of buildAdjacency(edges)) {
    degrees.set(id, neighbors.size)
  }
  return degrees
}

// Labels stay hidden across the overview zoom (where zoomToFit lands ~1x) so the
// graph reads as a clean constellation, and fade in only once the user has
// deliberately zoomed into a neighbourhood. Selected/hovered nodes bypass this.
export function labelAlpha(globalScale: number): number {
  const FADE_START = 2.6
  const FADE_END = 4.0
  if (globalScale <= FADE_START) return 0
  if (globalScale >= FADE_END) return 1
  return (globalScale - FADE_START) / (FADE_END - FADE_START)
}

// Deterministic [0, 1) hash of a node id. Used to give the population "dust" a
// stable per-point size/brightness jitter so 10k dots read as a star field
// instead of a uniform stipple — identical every render (no layout churn).
export function hashUnit(id: string): number {
  let h = 2166136261
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return ((h >>> 0) % 100000) / 100000
}

export function ambientPulse(id: string, now: number): number {
  const phase = hashUnit(id) * Math.PI * 2
  return 0.875 + Math.sin((now / 2400) * Math.PI * 2 + phase) * 0.125
}

export function linkParticleCount(weight: number, synthetic: boolean | undefined, isPopEdge: boolean): number {
  if (synthetic || isPopEdge) return 0
  return clamp01(weight) > 0.8 ? 1 : 0
}

export function spawnProgress(spawnedAt: number | undefined, now: number): number {
  if (spawnedAt == null) return 1
  const linear = clamp01((now - spawnedAt) / 600)
  return 1 - (1 - linear) ** 3
}

export function linkWidth(weight: number | null | undefined): number {
  return 0.35 + clamp01(weight) * 0.6
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

export function linkColor(_relation_type: string, weight: number | null | undefined, dimmed: boolean): string {
  return withAlpha('#8a96c8', dimmed ? 0.03 : 0.06 + clamp01(weight) * 0.1)
}

export interface GraphPhysics {
  chargeStrength: number
  linkDistance: number
  centerStrength: number
  collidePadding: number
}

export const DEFAULT_PHYSICS: GraphPhysics = {
  chargeStrength: -70,
  linkDistance: 42,
  centerStrength: 0.08,
  collidePadding: 2.5,
}

// Synthetic "visual affinity" links only exist to keep sparse graphs from
// flying apart — they carry no semantic meaning, so they must whisper. We ignore
// the endpoint colors entirely and paint a single cool slate at a hair of alpha,
// blended toward the endpoints only faintly so the web has subtle depth without
// ever becoming the loud green/red yarn ball it used to be.
export function syntheticLinkColor(_sourceColor: string, _targetColor: string, dimmed: boolean): string {
  return withAlpha('#8a96c8', dimmed ? 0.02 : 0.05)
}

function stableNodeSortKey(node: Pick<NodeProp, 'id' | 'stance' | 'type'>): string {
  return `${node.stance || node.type || ''}:${node.id}`
}

export function buildSyntheticLinks(
  nodes: ReadonlyArray<NodeProp>,
  edges: ReadonlyArray<EdgeProp>,
): SimLink[] {
  // Synthetic "visual affinity" links are a fallback for the sparse agent graph
  // only. The dense population layer must never receive them — at 10k nodes that
  // would mean tens of thousands of invisible links dragging layout, hit-testing
  // and paint. Restrict candidates (and the density check) to non-population.
  // 人口レイヤーが出ている間は hairball の密度は人口が担う。ここで synthetic を
  // 足すとエージェント同士だけが強く凝集し、人口の球から分離した団子になるため
  // 生成しない（実エッジ + pop-edge に任せて球へ混ざらせる）。
  if (nodes.some((node) => node.tier === 'population')) return []
  const linkable = nodes.filter((node) => node.tier !== 'population')
  if (linkable.length < 3) return []
  const realEdges = edges.filter((edge) => !(edge.id?.startsWith('pop-edge-') ?? false))

  const realPairs = new Set<string>()
  const degree = new Map(linkable.map((node) => [node.id, 0]))
  const pairKey = (a: string, b: string) => [a, b].sort().join('::')

  for (const edge of realEdges) {
    const source = endpointId(edge.source)
    const target = endpointId(edge.target)
    if (!source || !target || source === target) continue
    realPairs.add(pairKey(source, target))
    degree.set(source, (degree.get(source) ?? 0) + 1)
    degree.set(target, (degree.get(target) ?? 0) + 1)
  }

  const ordered = [...linkable].sort((a, b) => stableNodeSortKey(a).localeCompare(stableNodeSortKey(b)))
  const synthetic: SimLink[] = []
  const syntheticPairs = new Set<string>()
  const targetNeighborCount = Math.min(MAX_SYNTHETIC_NEIGHBORS, Math.max(3, Math.ceil(linkable.length / 14)))
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
      addSynthetic(source, target, Math.max(0.1, 0.3 - offset * 0.03))
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

interface MergeGraphDataCache {
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
  return {
    ...next,
    ...(next.tier !== 'population' && typeof performance !== 'undefined'
      ? { spawnedAt: performance.now() }
      : {}),
  }
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
