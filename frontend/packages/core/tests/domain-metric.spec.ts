/** 领域纯函数：指标与趋势（格式化 / 紧凑缩写 / 趋势方向与语义色 / 迷你折线）+ 指标契约套件。 */

import { describeMetricContract, type MetricContractTarget } from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

import {
  METRIC_COMPARE_LABELS,
  METRIC_EMPTY_TEXT,
  METRIC_FORMATS,
  SPARKLINE_DEFAULT_HEIGHT,
  SPARKLINE_DEFAULT_WIDTH,
  buildSparkline,
  clampMetricRatio,
  compactMetricValue,
  formatMetricValue,
  interpolateMetricValue,
  isMetricEmpty,
  normalizeTrend,
  resolveMetricTrend,
} from '../src'

/** 契约目标：指标与趋势领域纯函数。 */
const metricTarget: MetricContractTarget = {
  format: (value, options) => formatMetricValue(value, options),
  trend: (compare) => resolveMetricTrend(compare),
  sparkline: (values, options) => buildSparkline(values, options),
}

describeMetricContract('指标契约（domain/metric）', () => metricTarget)

describe('数值格式化', () => {
  it('空值判定与占位', () => {
    expect(isMetricEmpty(null)).toBe(true)
    expect(isMetricEmpty(undefined)).toBe(true)
    expect(isMetricEmpty('')).toBe(true)
    expect(isMetricEmpty('abc')).toBe(true)
    expect(isMetricEmpty(0)).toBe(false)
    expect(isMetricEmpty('12')).toBe(false)
    expect(formatMetricValue(null, { format: 'number' })).toBe(METRIC_EMPTY_TEXT)
    expect(formatMetricValue('abc', { format: 'number' })).toBe(METRIC_EMPTY_TEXT)
  })

  it('四种口径与精度夹取', () => {
    expect(formatMetricValue(1234.5, { format: 'number' })).toBe('1,234.5')
    expect(formatMetricValue(1234.5, { format: 'amount' })).toBe('¥1,234.50')
    expect(formatMetricValue(1234.5, { format: 'amount', precision: 0 })).toBe('¥1,235')
    expect(formatMetricValue(1234.5, { format: 'amount', precision: 99 })).toBe('¥1,234.500000')
    expect(formatMetricValue(0.125, { format: 'percent' })).toBe('12.50%')
    expect(formatMetricValue(1234.5, { format: 'custom', custom: (value) => `#${value}` })).toBe('#1234.5')
    expect(formatMetricValue(1234.5, { format: 'custom' })).toBe('1,234.5')
    expect(formatMetricValue(1234.5, { format: 'number', prefix: '¥', unit: '元' })).toBe('¥1,234.5元')
    expect(METRIC_FORMATS).toHaveLength(4)
  })

  it('紧凑缩写（万 / 亿）与阈值', () => {
    expect(compactMetricValue(9999)).toBe('9,999')
    expect(compactMetricValue(10_000)).toBe('1万')
    expect(compactMetricValue(12_345)).toBe('1.2万')
    expect(compactMetricValue(123_000_000)).toBe('1.2亿')
    expect(compactMetricValue(Number.NaN)).toBe(METRIC_EMPTY_TEXT)
    expect(formatMetricValue(12_345, { format: 'number', compact: true })).toBe('1.2万')
    expect(formatMetricValue(9999, { format: 'number', compact: true })).toBe('9,999')
  })

  it('趋势序列归一', () => {
    expect(normalizeTrend([1, '2', Number.NaN, null])).toEqual([1, 2, 0])
    expect(normalizeTrend('bad')).toEqual([])
  })
})

describe('趋势方向与语义色', () => {
  it('升 / 降 / 持平与文案', () => {
    expect(resolveMetricTrend(undefined)).toBeUndefined()
    expect(resolveMetricTrend({ kind: 'mom', value: Number.NaN })).toBeUndefined()

    const up = resolveMetricTrend({ kind: 'mom', value: 12.5 })
    expect(up).toMatchObject({ direction: 'up', semantic: 'success', token: '--bms-color-success' })
    expect(up?.text).toBe(`${METRIC_COMPARE_LABELS.mom} +12.5%`)

    const down = resolveMetricTrend({ kind: 'yoy', value: -5 })
    expect(down).toMatchObject({ direction: 'down', semantic: 'danger', token: '--bms-color-danger' })
    expect(down?.text).toBe(`${METRIC_COMPARE_LABELS.yoy} -5.0%`)

    const flat = resolveMetricTrend({ kind: 'mom', value: 0 })
    expect(flat).toMatchObject({ direction: 'flat', semantic: 'info' })
    expect(flat?.text).toContain('持平')
  })

  it('higherIsBetter 反转（下降为好）', () => {
    expect(resolveMetricTrend({ kind: 'mom', value: -5, higherIsBetter: false })?.semantic).toBe('success')
    expect(resolveMetricTrend({ kind: 'mom', value: 5, higherIsBetter: false })?.semantic).toBe('danger')
  })
})

describe('数字滚动插值与迷你折线', () => {
  it('比例夹取与插值', () => {
    expect(clampMetricRatio(-1)).toBe(0)
    expect(clampMetricRatio(2)).toBe(1)
    expect(clampMetricRatio(Number.NaN)).toBe(0)
    expect(interpolateMetricValue(0, 100, 0.25)).toBe(25)
    expect(interpolateMetricValue(0, 100, 5)).toBe(100)
    expect(interpolateMetricValue(Number.NaN, 100, 0.5)).toBe(100)
  })

  it('折线几何与退化（不足 2 点 / 全等值）', () => {
    expect(buildSparkline([1])).toBeUndefined()
    expect(buildSparkline([2, 2, 2])).toBeUndefined()
    expect(buildSparkline([Number.NaN, Number.NaN])).toBeUndefined()

    const geometry = buildSparkline([1, 3, 2, 5])
    expect(geometry?.width).toBe(SPARKLINE_DEFAULT_WIDTH)
    expect(geometry?.height).toBe(SPARKLINE_DEFAULT_HEIGHT)
    expect(geometry?.points).toHaveLength(4)
    expect(geometry?.line.startsWith('M ')).toBe(true)
    expect(geometry?.line).toContain(' L ')
    expect(geometry?.area.endsWith('Z')).toBe(true)
    expect(
      geometry?.points.every((point) => point.x <= SPARKLINE_DEFAULT_WIDTH && point.y <= SPARKLINE_DEFAULT_HEIGHT),
    ).toBe(true)
  })
})
