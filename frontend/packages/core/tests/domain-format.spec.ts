/** 格式化纯函数用例（02-6）。 */

import { describe, expect, it } from 'vitest'

import {
  EMPTY_PLACEHOLDER,
  formatAmount,
  formatDateTime,
  formatDuration,
  formatFileSize,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  mask,
} from '../src'

describe('日期时间格式化', () => {
  it('按 locale / 时区输出，非法值占位', () => {
    expect(formatDateTime('2026-01-02T03:04:05Z', { locale: 'en-US', timezone: 'UTC' })).toContain('2026')
    expect(formatDateTime('not-a-date')).toBe(EMPTY_PLACEHOLDER)
  })
})

describe('数值 / 金额 / 百分比', () => {
  it('金额（货币 + 精度）', () => {
    expect(formatAmount(1234.5, { locale: 'en-US', currency: 'USD' })).toBe('$1,234.50')
    expect(formatAmount(Number.NaN)).toBe(EMPTY_PLACEHOLDER)
  })

  it('千分位与百分比', () => {
    expect(formatNumber(1234567, { locale: 'en-US' })).toBe('1,234,567')
    expect(formatPercent(0.12, { locale: 'en-US', precision: 0 })).toBe('12%')
  })
})

describe('文件大小 / 时长', () => {
  it('文件大小', () => {
    expect(formatFileSize(512)).toBe('512 B')
    expect(formatFileSize(1536)).toBe('1.50 KB')
    expect(formatFileSize(-1)).toBe(EMPTY_PLACEHOLDER)
  })

  it('时长', () => {
    expect(formatDuration(3_723_000)).toBe('1h 2m 3s')
    expect(formatDuration(5000)).toBe('5s')
    expect(formatDuration(-1)).toBe(EMPTY_PLACEHOLDER)
  })
})

describe('相对时间 / 脱敏', () => {
  it('相对时间', () => {
    const base = new Date('2026-01-10T00:00:00Z')
    const text = formatRelativeTime('2026-01-07T00:00:00Z', { locale: 'en-US', base })
    expect(text).toContain('3')
  })

  it('脱敏保留首尾', () => {
    expect(mask('13800138000', { head: 3, tail: 4 })).toBe('138****8000')
    expect(mask('ab')).toBe('**')
  })
})
