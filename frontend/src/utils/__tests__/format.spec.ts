import { describe, expect, it } from 'vitest'

import { parseServerDate } from '../format'

describe('parseServerDate', () => {
  it('interprets naive server timestamps as UTC', () => {
    expect(parseServerDate('2026-06-29T12:00:00')).toBe(Date.parse('2026-06-29T12:00:00Z'))
  })

  it('preserves timestamps that already include UTC or offset suffixes', () => {
    expect(parseServerDate('2026-06-29T12:00:00Z')).toBe(Date.parse('2026-06-29T12:00:00Z'))
    expect(parseServerDate('2026-06-29T12:00:00+09:00')).toBe(Date.parse('2026-06-29T12:00:00+09:00'))
  })

  it('returns null for invalid values', () => {
    expect(parseServerDate('invalid-date')).toBeNull()
  })
})
