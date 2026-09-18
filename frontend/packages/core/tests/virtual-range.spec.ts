/** 虚拟列表可视区计算用例（04_01_02）。 */

import { describe, expect, it } from 'vitest'

import { computeVirtualRange } from '../src'

describe('computeVirtualRange 定高快路径', () => {
  it('按滚动偏移与视口计算起止（含缓冲）', () => {
    const range = computeVirtualRange({ scrollTop: 200, viewportHeight: 100, count: 100, itemHeight: 20, buffer: 4 })
    expect(range.start).toBe(6)
    expect(range.end).toBe(19)
    expect(range.offsetTop).toBe(120)
    expect(range.totalHeight).toBe(2000)
  })

  it('顶部与底部夹取', () => {
    const top = computeVirtualRange({ scrollTop: -50, viewportHeight: 100, count: 3, itemHeight: 20, buffer: 4 })
    expect(top.start).toBe(0)
    expect(top.end).toBe(3)

    const bottom = computeVirtualRange({ scrollTop: 10_000, viewportHeight: 100, count: 3, itemHeight: 20, buffer: 0 })
    expect(bottom.start).toBe(2)
    expect(bottom.end).toBe(3)
  })

  it('空数据返回零值', () => {
    expect(computeVirtualRange({ scrollTop: 0, viewportHeight: 100, count: 0, itemHeight: 20 })).toEqual({
      start: 0,
      end: 0,
      offsetTop: 0,
      totalHeight: 0,
    })
  })
})

describe('computeVirtualRange 动态高度路径', () => {
  const offsets = [0, 30, 80, 110, 160, 200, 260, 300]

  it('按累计偏移二分定位起始项', () => {
    const range = computeVirtualRange({ scrollTop: 100, viewportHeight: 80, count: 7, offsets, buffer: 0 })
    expect(range.start).toBe(2)
    expect(range.offsetTop).toBe(80)
    expect(range.totalHeight).toBe(300)
    expect(range.end).toBe(5)
  })

  it('缓冲扩张并夹取', () => {
    const range = computeVirtualRange({ scrollTop: 100, viewportHeight: 80, count: 7, offsets, buffer: 4 })
    expect(range.start).toBe(0)
    expect(range.end).toBe(7)
  })

  it('偏移缺失时退化为估算定高', () => {
    const range = computeVirtualRange({ scrollTop: 0, viewportHeight: 88, count: 5, buffer: 0 })
    expect(range.totalHeight).toBe(5 * 44)
    expect(range.start).toBe(0)
    expect(range.end).toBe(2)
  })
})
