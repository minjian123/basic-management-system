/** 可视区投影用例（迁自 `ui-ep` 容器滚动用例的组合式断言；Kiwi 覆盖随容器件套件）。 */

import { effectScope, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { useVirtualRange } from '../src'

describe('useVirtualRange（投影）', () => {
  it('定高：范围 / 偏移 / 总量 / 索引', () => {
    const range = effectScope(true).run(() =>
      useVirtualRange({ itemCount: 100, itemHeight: 20, buffer: 2 }),
    )!
    range.setViewport(200, 100)
    expect(range.startIndex.value).toBe(8)
    expect(range.endIndex.value).toBe(18)
    expect(range.offsetY.value).toBe(160)
    expect(range.totalHeight.value).toBe(2000)
    expect(range.offsetOf(50)).toBe(1000)
    expect(range.indexAt(999)).toBe(49)
  })

  it('动态高度：二分定位与估值回退；空列表', () => {
    const range = effectScope(true).run(() =>
      useVirtualRange({
        itemCount: 3,
        itemHeight: 10,
        buffer: 0,
        heights: [30, undefined, 50],
        estimated: 25,
      }),
    )!
    expect(range.totalHeight.value).toBe(105)
    expect(range.offsetOf(1)).toBe(30)
    expect(range.offsetOf(2)).toBe(55)
    expect(range.indexAt(56)).toBe(2)

    const empty = effectScope(true).run(() =>
      useVirtualRange({ itemCount: 0, itemHeight: 20, buffer: 0 }),
    )!
    expect(empty.totalHeight.value).toBe(0)
    expect(empty.indexAt(100)).toBe(0)
    empty.setViewport(50, 100)
    expect(empty.startIndex.value).toBe(0)
    expect(empty.endIndex.value).toBe(0)
  })

  it('响应式入参：项数 / 滚动位置变化驱动重算', () => {
    const count = ref(10)
    const range = effectScope(true).run(() =>
      useVirtualRange({ itemCount: count, itemHeight: 10, buffer: 1 }),
    )!
    expect(range.endIndex.value).toBe(3)
    count.value = 2
    expect(range.endIndex.value).toBe(2)
    range.setViewport(50, 10)
    expect(range.indexAt(50)).toBe(1)
  })
})
