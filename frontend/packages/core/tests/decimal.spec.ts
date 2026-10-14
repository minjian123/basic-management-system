/** 十进制定点纯函数用例（06_02_02）。 */

import { describe, expect, it } from 'vitest'

import {
  compareDecimal,
  decimalPlaces,
  formatDecimal,
  fromMinorUnits,
  isDecimal,
  isDecimalInRange,
  normalizeDecimal,
  padDecimal,
  sanitizePrecision,
  toChineseUpper,
  toMinorUnits,
} from '../src'

describe('normalizeDecimal', () => {
  it('按精度四舍五入并去尾零', () => {
    expect(normalizeDecimal('1234.5678', 2)).toBe('1234.57')
    expect(normalizeDecimal('1234.5678', 4)).toBe('1234.5678')
    expect(normalizeDecimal('1.005', 2)).toBe('1.01')
    expect(normalizeDecimal('2.10', 2)).toBe('2.1')
    expect(normalizeDecimal('3', 0)).toBe('3')
    expect(normalizeDecimal('-1.234', 2)).toBe('-1.23')
    expect(normalizeDecimal('-0.001', 2)).toBe('0')
  })

  it('非法输入返回空串；精度夹取', () => {
    expect(normalizeDecimal('abc', 2)).toBe('')
    expect(normalizeDecimal('', 2)).toBe('')
    expect(sanitizePrecision(-1)).toBe(0)
    expect(sanitizePrecision(9)).toBe(6)
    expect(sanitizePrecision(Number.NaN)).toBe(0)
  })

  it('厘 / 毫精度', () => {
    expect(normalizeDecimal('1.2345', 3)).toBe('1.235')
    expect(normalizeDecimal('1.2345', 4)).toBe('1.2345')
  })
})

describe('toMinorUnits / fromMinorUnits', () => {
  it('字符串移位往返（含厘 / 毫）', () => {
    expect(toMinorUnits('1.23', 2)).toBe(123n)
    expect(toMinorUnits('1.2345', 4)).toBe(12345n)
    expect(toMinorUnits('-0.05', 2)).toBe(-5n)
    expect(fromMinorUnits(12345n, 4)).toBe('1.2345')
    expect(fromMinorUnits(-5n, 2)).toBe('-0.05')
    expect(fromMinorUnits(7n, 0)).toBe('7')
  })

  it('大数不失真（超双精度）', () => {
    const text = '9007199254740993000.01'
    expect(fromMinorUnits(toMinorUnits(text, 2), 2)).toBe(text)
  })
})

describe('compareDecimal / isDecimalInRange', () => {
  it('定点比较', () => {
    expect(compareDecimal('1.10', '1.1')).toBe(0)
    expect(compareDecimal('1.09', '1.1')).toBe(-1)
    expect(compareDecimal('2', '1.9999')).toBe(1)
  })

  it('范围判定（空值 / 非法越界）', () => {
    expect(isDecimalInRange('1.5', { min: '1', max: '2' })).toBe(true)
    expect(isDecimalInRange('0.99', { min: '1', max: '2' })).toBe(false)
    expect(isDecimalInRange('2.01', { min: '1', max: '2' })).toBe(false)
    expect(isDecimalInRange('abc', { min: '0' })).toBe(false)
    expect(isDecimal('12.345')).toBe(true)
    expect(isDecimal('1.2.3')).toBe(false)
  })
})

describe('decimalPlaces（精度位数文本判定，11_03）', () => {
  it('浮点乘法误判场景：0.29 配 precision=2 判为 2 位', () => {
    // `Number.isInteger(0.29 * 100)` → 28.999999999999996 → 会误判超精度
    expect(decimalPlaces(0.29)).toEqual({ fraction: 2, valid: true })
    expect(Number.isInteger(0.29 * 100)).toBe(false)
  })

  it('去尾零后计位；非法输入 valid=false', () => {
    expect(decimalPlaces('1.500')).toEqual({ fraction: 1, valid: true })
    expect(decimalPlaces('1.234')).toEqual({ fraction: 3, valid: true })
    expect(decimalPlaces('abc')).toEqual({ fraction: 0, valid: false })
  })
})

describe('formatDecimal / padDecimal（定点展示，不经浮点）', () => {
  it('千分位分组保留精度', () => {
    expect(formatDecimal('1234567.5', { precision: 2 })).toBe('1,234,567.50')
    expect(formatDecimal('1000', { precision: 2 })).toBe('1,000.00')
    expect(formatDecimal('-1234.5', { precision: 2 })).toBe('-1,234.50')
    expect(formatDecimal('abc')).toBe('')
  })

  it('未指定精度时按去尾零位数展示', () => {
    expect(formatDecimal('1234.500')).toBe('1,234.5')
    expect(formatDecimal('1000')).toBe('1,000')
  })

  it('padDecimal 按精度补齐（不四舍五入）', () => {
    expect(padDecimal('1.5', 2)).toBe('1.50')
    expect(padDecimal('100', 2)).toBe('100.00')
    expect(padDecimal('100', 0)).toBe('100')
    expect(padDecimal('abc', 2)).toBe('')
  })
})

describe('toChineseUpper（金额中文大写，纯函数）', () => {
  it('常规金额与整元', () => {
    expect(toChineseUpper('12345.67')).toBe('壹万贰仟叁佰肆拾伍元陆角柒分')
    expect(toChineseUpper('100')).toBe('壹佰元整')
    expect(toChineseUpper('0')).toBe('零元整')
  })

  it('节间补零与角分缺位', () => {
    expect(toChineseUpper('1000000')).toBe('壹佰万元整')
    expect(toChineseUpper('10000.05')).toBe('壹万元零伍分')
    expect(toChineseUpper('0.5')).toBe('零元伍角')
  })

  it('负数与非法输入', () => {
    expect(toChineseUpper('-1.01')).toBe('负壹元零壹分')
    expect(toChineseUpper('abc')).toBe('')
  })
})
