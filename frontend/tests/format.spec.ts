/** 格式化工具用例（Kiwi 721）：日期时区 / 数值金额 / 边界（双端同款）。 */

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  configureFormatDefaults,
  formatAmount,
  formatDate,
  formatDateRange,
  formatDateTime,
  formatDuration,
  formatFileSize,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  getFormatDefaults,
  maskValue,
  resetFormatDefaults,
} from '@/utils/format'
import { TIMEZONE_STORAGE_KEY, useTimezone } from '@/utils/useTimezone'

describe('格式化工具（Kiwi 721）', () => {
  beforeEach(() => {
    localStorage.clear()
    resetFormatDefaults()
  })

  afterEach(() => {
    resetFormatDefaults()
  })

  it('① 日期时间：时区换算 / seconds / 自定义 pattern', () => {
    const value = '2026-09-11T06:30:45Z'
    expect(formatDateTime(value, { timezone: 'Asia/Shanghai' })).toBe('2026-09-11 14:30')
    expect(formatDateTime(value, { timezone: 'UTC' })).toBe('2026-09-11 06:30')
    expect(formatDateTime(value, { timezone: 'Asia/Shanghai', seconds: true })).toBe('2026-09-11 14:30:45')
    expect(formatDateTime(value, { timezone: 'Asia/Shanghai', pattern: 'MM/dd/yyyy' })).toBe('09/11/2026')
  })

  it('③ 空值 / 非法值占位；④ formatDate / formatDateRange', () => {
    expect(formatDateTime(null)).toBe('—')
    expect(formatDateTime('not-a-date')).toBe('—')
    expect(formatDateTime(undefined, { placeholder: '暂无' })).toBe('暂无')

    expect(formatDate('2026-09-11T06:30:45Z', { timezone: 'Asia/Shanghai' })).toBe('2026-09-11')
    expect(formatDateRange(['2026-09-01T00:00:00Z', '2026-09-11T06:30:45Z'], { timezone: 'UTC' })).toBe(
      '2026-09-01 ~ 2026-09-11',
    )
    expect(formatDateRange(null)).toBe('—')
  })

  it('⑤ 相对时间：刚刚 / 分钟 / 小时 / 昨天', () => {
    const now = new Date('2026-09-11T14:40:00Z')
    const options = { timezone: 'Asia/Shanghai', now }
    expect(formatRelativeTime('2026-09-11T14:39:30Z', options)).toBe('刚刚')
    expect(formatRelativeTime('2026-09-11T14:35:00Z', options)).toContain('分钟')
    expect(formatRelativeTime('2026-09-11T12:40:00Z', options)).toContain('小时')
    expect(formatRelativeTime('2026-09-10T06:30:00Z', options)).toBe('昨天 14:30')
    expect(formatRelativeTime('2026-09-01T06:30:00Z', options)).toBe('2026-09-01')
  })

  it('⑥ formatNumber：千分位 / 精度 / 非数值占位', () => {
    expect(formatNumber(1234567.891, { precision: 2 })).toBe('1,234,567.89')
    expect(formatNumber(1234567)).toBe('1,234,567')
    expect(formatNumber('abc')).toBe('—')
    expect(formatNumber(0)).toBe('0')
  })

  it('⑦ formatAmount：精度 / 符号 / 字符串入参 / 负数 / 超大数', () => {
    expect(formatAmount('1234.5')).toBe('¥1,234.50')
    expect(formatAmount(1234.5, { symbol: false })).toBe('1,234.50')
    expect(formatAmount(1234.5, { precision: 0 })).toBe('¥1,235')
    expect(formatAmount(-1234.5)).toBe('-¥1,234.50')
    expect(formatAmount('bad')).toBe('—')
    expect(() => formatAmount('999999999999999999999999')).not.toThrow()
    expect(typeof formatAmount('999999999999999999999999')).toBe('string')
  })

  it('⑧ formatPercent：ratio 两种口径', () => {
    expect(formatPercent(0.1234, { ratio: true })).toBe('12.34%')
    expect(formatPercent(12.34)).toBe('12.34%')
    expect(formatPercent(null)).toBe('—')
  })

  it('⑨ 文件大小 / ⑩ 时长 / ⑪ 脱敏', () => {
    expect(formatFileSize(1024)).toBe('1 KB')
    expect(formatFileSize(1536)).toBe('1.5 KB')
    expect(formatFileSize(0)).toBe('0 B')
    expect(formatFileSize(-1)).toBe('—')

    expect(formatDuration(3661)).toBe('1 小时 1 分 1 秒')
    expect(formatDuration(0)).toBe('0 秒')
    expect(formatDuration(null)).toBe('—')

    expect(maskValue('13812345678', 'phone')).toBe('138****5678')
    expect(maskValue('zhang@example.com', 'email')).toBe('z***@example.com')
    expect(maskValue('110101199001011234', 'idcard')).toBe('1101************34')
    expect(maskValue('abcd', 'generic')).toBe('a**d')
    expect(maskValue('', 'generic')).toBe('—')
  })

  it('⑫ configureFormatDefaults 生效与复位；⑬ useTimezone 优先级与持久化', () => {
    configureFormatDefaults({ locale: 'en-US', timezone: 'UTC' })
    expect(getFormatDefaults().timezone).toBe('UTC')
    expect(formatDateTime('2026-09-11T06:30:45Z')).toBe('2026-09-11 06:30')
    expect(formatDuration(61)).toBe('1 m 1 s')
    resetFormatDefaults()

    localStorage.setItem(TIMEZONE_STORAGE_KEY, 'Asia/Shanghai')
    const tz = useTimezone()
    expect(tz.timezone).toBe('Asia/Shanghai')
    expect(tz.isPlaceholder).toBe(true)
    tz.setTimezone('UTC')
    expect(localStorage.getItem(TIMEZONE_STORAGE_KEY)).toBe('UTC')
    expect(getFormatDefaults().timezone).toBe('UTC')

    const explicit = useTimezone({ timezone: 'Asia/Shanghai', persist: false })
    expect(explicit.timezone).toBe('Asia/Shanghai')
  })
})
