import { getStanceColor } from '../constants/stances'

export interface NodeProp {
  id: string
  label: string
  type: string
  importance_score: number
  activity_score: number
  stance?: string
  status?: string
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
] as const

const EDGE_PROP_KEYS = ['id', 'source', 'target', 'relation_type', 'weight', 'label'] as const

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

export function nodeRadius(
  node: Pick<NodeProp, 'importance_score' | 'activity_score' | 'status'>,
  degree = 0,
): number {
  const importance = clamp01(node.importance_score ?? 0.4)
  const activityBoost = (node.activity_score ?? 0) > 0 || node.status === 'speaking' ? 3 : 0
  // Obsidian 同様、接続数の多いハブほど大きく（sqrt スケール、上限付き）
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

/** ズームレベルに応じたラベル不透明度。0.45 未満で非表示、0.45-0.9 で連続フェード、以降フル表示。 */
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
  // Obsidian 風: エッジは細く半透明で静かに。フォーカス外は強くフェード。
  const alpha = dimmed ? 0.06 : Math.min(0.42, 0.14 + clamp01(weight) * 0.28)
  return withAlpha(base, alpha)
}

export interface GraphPhysics {
  /** 反発力（負値）。Obsidian の「反発力」スライダー相当 */
  chargeStrength: number
  /** リンク基本距離。weight が低いほど距離が伸びる */
  linkDistance: number
  /** 中心引力 */
  centerStrength: number
  /** 衝突回避の余白 */
  collidePadding: number
}

export const DEFAULT_PHYSICS: GraphPhysics = {
  chargeStrength: -220,
  linkDistance: 60,
  centerStrength: 0.04,
  collidePadding: 4,
}

function endpointId(end: string | { id?: string | number } | undefined): string {
  if (end == null) return ''
  if (typeof end === 'string') return end
  if (typeof end === 'number') return String(end)
  return String(end.id ?? '')
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

export function mergeGraphData(
  prevNodes: ReadonlyArray<SimNode>,
  newNodes: ReadonlyArray<NodeProp>,
  newEdges: ReadonlyArray<EdgeProp>,
): { nodes: SimNode[]; links: SimLink[] } {
  const prevById = new Map(prevNodes.map((n) => [n.id, n]))
  const nodes: SimNode[] = newNodes.map((n) => {
    const existing = prevById.get(n.id)
    if (existing) {
      // Mutate in place so force-graph keeps the same object reference,
      // preserving x/y/vx/vy/fx/fy/index across reactive updates.
      existing.label = n.label
      existing.type = n.type
      existing.importance_score = n.importance_score
      existing.activity_score = n.activity_score
      existing.stance = n.stance
      existing.status = n.status
      return existing
    }
    return { ...n }
  })
  const links: SimLink[] = newEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    relation_type: e.relation_type,
    weight: e.weight,
    label: e.label,
  }))
  return { nodes, links }
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
