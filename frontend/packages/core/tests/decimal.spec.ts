/** 十进制定点纯函数用例（06_02_02）。 */

import { describe, expect, it } from 'vitest'

import {
  compareDecimal,
  fromMinorUnits,
  isDecimal,
  isDecimalInRange,
  normalizeDecimal,
  sanitizePrecision,
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
