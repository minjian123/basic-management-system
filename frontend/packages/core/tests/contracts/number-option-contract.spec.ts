/** 数字域（`domain/number`）与选项域（`domain/option`）纯函数契约用例（05_02）。 */

import { describe, expect, it } from 'vitest'

import {
  applyPrecision,
  clampNumber,
  filterOptions,
  formatNumber,
  groupOptions,
  inNumberRange,
  isOptionSelectable,
  labelOfOption,
  normalizeOptionValue,
  orderOptionValues,
  parseFormattedNumber,
  parseNumberInput,
  reachMaxCount,
  type OptionItem,
} from '../../src'

const OPTIONS: OptionItem[] = [
  { value: 'a', label: 'A' },
  { value: 'b', label: 'B', group: '组一' },
  { value: 'c', label: 'C', group: '组一' },
  { value: 'd', label: 'D', disabled: true },
]

describe('数字域契约（number）', () => {
  it('解析：中间态 / 数值 / 非法字符（取合法前缀）', () => {
    expect(parseNumberInput('').value).toBeNull()
    expect(parseNumberInput('-').value).toBeNull()
    expect(parseNumberInput('.').value).toBeNull()
    expect(parseNumberInput('-').invalid).toBe(false)
    expect(parseNumberInput('12').value).toBe(12)

    const partial = parseNumberInput('1.2.3', { precision: 2 })
    expect(partial.value).toBe(1.2)
    expect(partial.invalid).toBe(true)

    const alpha = parseNumberInput('abc')
    expect(alpha.value).toBeNull()
    expect(alpha.invalid).toBe(true)
  })

  it('精度：四舍五入到指定小数位（默认整数）', () => {
    expect(applyPrecision(1.25, 1)).toBe(1.3)
    expect(applyPrecision(1.44, 1)).toBe(1.4)
    expect(applyPrecision(1.6)).toBe(2)
    expect(applyPrecision(1.5, -1)).toBe(2)
  })

  it('越界：钳制 / 范围判定 / `clamp=false` 保留原值并标记', () => {
    expect(clampNumber(20, 0, 10)).toBe(10)
    expect(clampNumber(-5, 0, 10)).toBe(0)
    expect(clampNumber(5)).toBe(5)
    expect(inNumberRange(5, 0, 10)).toBe(true)
    expect(inNumberRange(11, 0, 10)).toBe(false)

    const clamped = parseNumberInput('20', { min: 0, max: 10, clamp: true })
    expect(clamped.value).toBe(10)
    expect(clamped.outOfRange).toBe(true)

    const loose = parseNumberInput('20', { min: 0, max: 10, clamp: false })
    expect(loose.value).toBe(20)
    expect(loose.outOfRange).toBe(true)
  })

  it('千分位：格式化与反解析（仅显示层）', () => {
    expect(formatNumber(1234567, { thousands: true })).toBe('1,234,567')
    expect(formatNumber(1234.5, { precision: 2, thousands: true })).toBe('1,234.50')
    expect(formatNumber(-1234.5, { precision: 1, thousands: true })).toBe('-1,234.5')
    expect(formatNumber(12)).toBe('12')
    expect(formatNumber(null)).toBe('')
    expect(parseFormattedNumber('1,234,567')).toBe('1234567')
    expect(parseNumberInput('1,234').value).toBe(1234)
  })
})

describe('选项域契约（option）', () => {
  it('归一：无效值剔除（单选 → `null`；多选 → 过滤）', () => {
    expect(normalizeOptionValue('a', OPTIONS, false)).toBe('a')
    expect(normalizeOptionValue('ghost', OPTIONS, false)).toBeNull()
    expect(normalizeOptionValue(['a', 'ghost'], OPTIONS, true)).toEqual(['a'])
    expect(normalizeOptionValue(null, OPTIONS, true)).toEqual([])
    expect(normalizeOptionValue('a', OPTIONS, true)).toEqual(['a'])
    expect(normalizeOptionValue(['a', 'b'], OPTIONS, false)).toBe('a')
  })

  it('多选：去重并按选项顺序保序（与勾选顺序无关）', () => {
    expect(orderOptionValues(['c', 'a', 'b', 'a'], OPTIONS)).toEqual(['a', 'b', 'c'])
    expect(normalizeOptionValue(['c', 'a'], OPTIONS, true)).toEqual(['a', 'c'])
  })

  it('文本：单值 / 多值（、）/ 未命中回退 / 空值', () => {
    expect(labelOfOption('b', OPTIONS)).toBe('B')
    expect(labelOfOption(['b', 'a'], OPTIONS)).toBe('A、B')
    expect(labelOfOption(null, OPTIONS)).toBe('')
    expect(labelOfOption('ghost', OPTIONS)).toBe('ghost')
  })

  it('分组：同组连续且顺序保持', () => {
    const groups = groupOptions(OPTIONS)
    expect(groups.map((item) => item.group)).toEqual(['', '组一', ''])
    expect(groups[1]?.items.map((item) => item.value)).toEqual(['b', 'c'])
  })

  it('上限与可选性：达上限拒绝未选项 / 已选项可取消 / 禁用项不可选', () => {
    expect(reachMaxCount(['a'], 1)).toBe(true)
    expect(reachMaxCount(['a'], 2)).toBe(false)
    expect(reachMaxCount(['a'])).toBe(false)
    expect(reachMaxCount(['a'], 0)).toBe(false)

    expect(isOptionSelectable(OPTIONS[2] as OptionItem, ['a'], 1)).toBe(false)
    expect(isOptionSelectable(OPTIONS[0] as OptionItem, ['a'], 1)).toBe(true)
    expect(isOptionSelectable(OPTIONS[3] as OptionItem, [], undefined)).toBe(false)
  })

  it('过滤：按文本包含匹配（大小写不敏感，空关键字返回全部）', () => {
    expect(filterOptions(OPTIONS, '').length).toBe(4)
    expect(filterOptions(OPTIONS, 'b').map((item) => item.value)).toEqual(['b'])
    expect(filterOptions(OPTIONS, 'A').map((item) => item.value)).toEqual(['a'])
    expect(filterOptions(OPTIONS, 'ghost').length).toBe(0)
  })
})
