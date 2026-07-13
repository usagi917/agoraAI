export const STANCE_ORDER = ['賛成', '条件付き賛成', '中立', '条件付き反対', '反対'] as const

type StanceLabel = typeof STANCE_ORDER[number]

export const STANCE_COLORS: Record<string, string> = {
  '賛成': '#34d399',
  '条件付き賛成': '#67e8f9',
  '中立': '#fbbf24',
  '条件付き反対': '#fb923c',
  '反対': '#fb7185',
}

const DEFAULT_STANCE_COLOR = '#6366f1'

const NUMERIC_STANCE_LABELS: ReadonlyArray<readonly [number, StanceLabel]> = [
  [1.0, '賛成'],
  [0.7, '条件付き賛成'],
  [0.5, '中立'],
  [0.3, '条件付き反対'],
  [0.0, '反対'],
]

export function numericToStanceLabel(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value !== 'number') return '中立'

  let closest = NUMERIC_STANCE_LABELS[0]
  for (const entry of NUMERIC_STANCE_LABELS) {
    if (Math.abs(value - entry[0]) < Math.abs(value - closest[0])) {
      closest = entry
    }
  }
  return closest[1]
}

export function getStanceColor(
  stance: string | null | undefined,
  fallback = DEFAULT_STANCE_COLOR,
): string {
  if (!stance) return fallback
  return STANCE_COLORS[stance] || fallback
}

export function getStanceSortIndex(stance: string): number {
  const index = STANCE_ORDER.indexOf(stance as StanceLabel)
  return index === -1 ? Number.MAX_SAFE_INTEGER : index
}
