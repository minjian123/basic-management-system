// kiwi_id: 777
/** 大屏播放领域用例（08-9-2）：轮播切页 / 单页时长 / 间隔归一 / 等比缩放。 */

import { describe, expect, it } from 'vitest'

import {
  computeScale,
  isRotationDue,
  nextPageId,
  normalizePlayInterval,
  pageDuration,
  pageIds,
  prevPageId,
  type ScreenPage,
} from '../src'

/** 契约页。 */
const pages: ScreenPage[] = [
  { id: 'p1', name: '首页' },
  { id: 'p2', name: '明细', duration: 3000 },
  { id: 'p3', name: '尾页' },
]

describe('轮播', () => {
  it('切页：环回与端点', () => {
    expect(pageIds(pages)).toEqual(['p1', 'p2', 'p3'])
    expect(nextPageId(pages, 'p1')).toBe('p2')
    expect(nextPageId(pages, 'p3')).toBe('p1')
    expect(nextPageId(pages, 'p3', false)).toBe('p3')
    expect(prevPageId(pages, 'p1')).toBe('p3')
    expect(prevPageId(pages, 'p1', false)).toBe('p1')
    expect(nextPageId(pages, 'ghost')).toBe('p1')
    expect(nextPageId([], 'p1')).toBe('p1')
  })

  it('单页时长：页自定义优先', () => {
    expect(pageDuration(pages[1], 5000)).toBe(3000)
    expect(pageDuration(pages[0], 5000)).toBe(5000)
    expect(pageDuration(undefined, 0)).toBe(5000)
  })

  it('轮播时机判定', () => {
    expect(isRotationDue(4999, 5000)).toBe(false)
    expect(isRotationDue(5000, 5000)).toBe(true)
    expect(isRotationDue(5000, 0)).toBe(false)
  })

  it('间隔归一（下限 1000）', () => {
    expect(normalizePlayInterval(0)).toBe(5000)
    expect(normalizePlayInterval(500)).toBe(1000)
    expect(normalizePlayInterval(8000)).toBe(8000)
    expect(normalizePlayInterval(undefined, 2000)).toBe(2000)
  })
})

describe('等比缩放', () => {
  it('contain 完整可见、cover 铺满', () => {
    const contain = computeScale({ width: 1920, height: 1080 }, { width: 960, height: 540 })
    expect(contain.scale).toBe(0.5)
    expect(contain.offsetX).toBe(0)
    expect(contain.offsetY).toBe(0)

    const wide = computeScale({ width: 1920, height: 1080 }, { width: 1000, height: 1000 })
    expect(wide.scale).toBeCloseTo(1000 / 1920)
    expect(wide.offsetY).toBeCloseTo((1000 - 1080 * (1000 / 1920)) / 2)

    const cover = computeScale({ width: 1920, height: 1080 }, { width: 1000, height: 1000 }, 'cover')
    expect(cover.scale).toBeCloseTo(1000 / 1080)
  })

  it('非法输入回落无缩放', () => {
    expect(computeScale({ width: 0, height: 1080 }, { width: 100, height: 100 })).toEqual({
      scale: 1,
      offsetX: 0,
      offsetY: 0,
    })
    expect(computeScale({ width: 1920, height: 1080 }, { width: 0, height: 0 })).toEqual({
      scale: 1,
      offsetX: 0,
      offsetY: 0,
    })
  })
})
