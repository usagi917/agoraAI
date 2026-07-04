import { describe, expect, it } from 'vitest'

import { formatPercent, parseServerDate } from '../format'

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

describe("formatPercent", () => {
  it("digits=0", () => expect(formatPercent(0.1234)).toBe("12%"))
  it("digits=1", () => expect(formatPercent(0.1234, 1)).toBe("12.3%"))
  it("null", () => expect(formatPercent(null)).toBe("n/a"))
  it("NaN", () => expect(formatPercent(NaN)).toBe("n/a"))
  it("zero", () => expect(formatPercent(0)).toBe("0%"))
})
