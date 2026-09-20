/**
 * 指标契约（`@bms/core/testing`）。
 *
 * 指标卡（`07_05`）/ 工作台统计卡 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 空值占位、格式化与紧凑缩写、趋势方向与语义色（含 `higherIsBetter` 反转）、迷你折线几何与退化。
 */

import { describe, expect, it } from 'vitest'

import type { MetricCompare, MetricFormatOptions, MetricTrend, SparklineGeometry } from '../src'

/** 指标契约面（结构化接口）。 */
export interface MetricContractTarget {
  /** 格式化数值。 */
  format(value: unknown, options: MetricFormatOptions): string
  /** 解析趋势。 */
  trend(compare: MetricCompare | undefined): MetricTrend | undefined
  /** 构建迷你折线。 */
  sparkline(values: readonly number[], options?: { width?: number; height?: number }): SparklineGeometry | undefined
}

/**
 * 指标契约（`07_05` 冻结）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeMetricContract(name: string, create: () => MetricContractTarget): void {
  describe(name, () => {
    it('空值占位与格式化口径', () => {
      const target = create()
      expect(target.format(null, { format: 'number' })).toBe('—')
      expect(target.format('abc', { format: 'number' })).toBe('—')
      expect(target.format(1234.5, { format: 'number' })).toBe('1,234.5')
      expect(target.format(1234.5, { format: 'amount' })).toBe('¥1,234.50')
      expect(target.format(0.125, { format: 'percent' })).toBe('12.50%')
      expect(target.format(1234.5, { format: 'custom', custom: (value) => `#${value}` })).toBe('#1234.5')
      expect(target.format(1234.5, { format: 'number', prefix: '¥', unit: '元' })).toBe('¥1,234.5元')
    })

    it('紧凑缩写', () => {
      const target = create()
      expect(target.format(12345, { format: 'number', compact: true })).toBe('1.2万')
      expect(target.format(123_000_000, { format: 'number', compact: true })).toBe('1.2亿')
      expect(target.format(9999, { format: 'number', compact: true })).toBe('9,999')
    })

    it('趋势方向与语义色（含 higherIsBetter 反转）', () => {
      const target = create()
      expect(target.trend(undefined)).toBeUndefined()

      const up = target.trend({ kind: 'mom', value: 12.5 })
      expect(up?.direction).toBe('up')
      expect(up?.semantic).toBe('success')
      expect(up?.token.startsWith('--bms-')).toBe(true)
      expect(up?.text).toContain('较上月')

      const down = target.trend({ kind: 'yoy', value: -5 })
      expect(down?.direction).toBe('down')
      expect(down?.semantic).toBe('danger')
      expect(down?.text).toContain('较去年同期')

      const inverted = target.trend({ kind: 'mom', value: -5, higherIsBetter: false })
      expect(inverted?.direction).toBe('down')
      expect(inverted?.semantic).toBe('success')

      const flat = target.trend({ kind: 'mom', value: 0 })
      expect(flat?.direction).toBe('flat')
      expect(flat?.semantic).toBe('info')
    })

    it('迷你折线几何与退化', () => {
      const target = create()
      expect(target.sparkline([1])).toBeUndefined()
      expect(target.sparkline([2, 2])).toBeUndefined()

      const geometry = target.sparkline([1, 3, 2, 5], { width: 100, height: 20 })
      expect(geometry).toBeDefined()
      expect(geometry?.points).toHaveLength(4)
      expect(geometry?.line.startsWith('M ')).toBe(true)
      expect(geometry?.area.endsWith('Z')).toBe(true)
      expect(geometry?.width).toBe(100)
      expect(geometry?.height).toBe(20)
      expect(geometry?.points.every((point) => point.x >= 0 && point.x <= 100 && point.y >= 0 && point.y <= 20)).toBe(
        true,
      )
    })
  })
}
