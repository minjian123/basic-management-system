import { describe, expect, it } from 'vitest'
import { formatDateTime, truncateText } from '../format'

describe('formatDateTime', () => {
  it('formats a Date object as YYYY-MM-DD HH:mm:ss', () => {
    const date = new Date(2026, 0, 5, 9, 30, 8)
    expect(formatDateTime(date)).toBe('2026-01-05 09:30:08')
  })

  it('accepts a timestamp number', () => {
    expect(formatDateTime(0)).toMatch(/^1970-01-01/)
  })

  it('returns an empty string for an invalid date', () => {
    expect(formatDateTime('not-a-date')).toBe('')
  })
})

describe('truncateText', () => {
  it('keeps short text unchanged', () => {
    expect(truncateText('hello', 10)).toBe('hello')
  })

  it('truncates long text with an ellipsis', () => {
    expect(truncateText('hello world', 5)).toBe('hello…')
  })
})
