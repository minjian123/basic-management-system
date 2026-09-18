/** 格式化工具（宿主默认基准注入）用例。 */

import { describe, expect, it } from 'vitest'

import { configureFormatDefaults, formatAmount, formatDate, formatDateTime, mask } from '@/utils/format'

describe('格式化工具', () => {
  it('默认基准可注入并生效', () => {
    configureFormatDefaults({ locale: 'en-US', timezone: 'UTC' })
    expect(formatDateTime('2026-01-02T03:04:05Z')).toContain('2026')
    expect(formatDate('2026-01-02T03:04:05Z')).toContain('2026')
    expect(formatAmount(12.5, { currency: 'USD' })).toBe('$12.50')
  })

  it('按覆盖基准格式化', () => {
    expect(formatDateTime('2026-01-02T03:04:05Z', { locale: 'en-US', timezone: 'UTC' })).toContain('2026')
  })

  it('脱敏透传', () => {
    expect(mask('13800138000', { head: 3, tail: 4 })).toBe('138****8000')
  })
})
