import { describe, expect, it } from 'vitest'
import { formatDate, isBlank } from '../format'

describe('formatDate', () => {
  it('formats a Date object as YYYY-MM-DD', () => {
    const date = new Date(2026, 0, 5)
    expect(formatDate(date)).toBe('2026-01-05')
  })

  it('accepts a timestamp number', () => {
    expect(formatDate(0)).toBe('1970-01-01')
  })

  it('returns an empty string for an invalid date', () => {
    expect(formatDate('not-a-date')).toBe('')
  })
})

describe('isBlank', () => {
  it('detects null, undefined and whitespace-only strings', () => {
    expect(isBlank(null)).toBe(true)
    expect(isBlank(undefined)).toBe(true)
    expect(isBlank('   ')).toBe(true)
    expect(isBlank(' bms ')).toBe(false)
  })
})
