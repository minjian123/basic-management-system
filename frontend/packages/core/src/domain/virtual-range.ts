/**
 * 虚拟列表可视区计算（框架无关核心领域层）。
 *
 * - 前缀和 + 二分查找：定高为「估值 = `itemHeight`」的特例（统一路径，数值等价）；
 * - 动态高度：由调用方注入高度数组（实测 / 估值混合，只读），滚动与测量变化由投影侧重算；
 * - 纯函数（不触 DOM、不用 Vue 响应式），供 `@bms/vue` 的 `useVirtualRange` 投影与后续
 *   虚拟化场景（如通用表格）复用。
 */

import type { ScrollMetrics } from './scroll-position'

/** 虚拟列表滚动度量（`VirtualList` 的 `scroll` / `reach-bottom` 载荷：尺寸 + 可视区索引） */
export interface VirtualScrollMetrics extends ScrollMetrics {
  /** 渲染起始索引（含缓冲） */
  startIndex: number
  /** 渲染结束索引（不含；slice 语义） */
  endIndex: number
}

export interface VirtualRangeInput {
  /** 项数 */
  itemCount: number
  /** 定高项高（px；估值缺省来源，`≥ 1`） */
  itemHeight: number
  /** 上 / 下缓冲项数（`≥ 0`） */
  buffer: number
  /** 动态高度数组（只读；`undefined` 项按估值；缺省 / `null` 走定高公式路径） */
  heights?: readonly (number | undefined)[] | null
  /** 动态估值（px；缺省 = `itemHeight`） */
  estimated?: number
  /** 滚动位置（px） */
  scrollTop: number
  /** 视口高度（px） */
  viewportHeight: number
}

export interface VirtualRangeResult {
  /** 渲染起始索引（含缓冲） */
  readonly startIndex: number
  /** 渲染结束索引（不含；slice 语义） */
  readonly endIndex: number
  /** 可视区起始项前缀偏移（px；`translateY`） */
  readonly offsetY: number
  /** 总高度（px；撑高占位） */
  readonly totalHeight: number
  /** 指定索引的前缀偏移（px） */
  offsetOf(index: number): number
  /** 指定滚动位置所在项索引（二分 / 公式） */
  indexAt(top: number): number
}

/** 计算可视区（纯函数：同输入同输出，不持有状态） */
export function computeVirtualRange(input: VirtualRangeInput): VirtualRangeResult {
  const count = Math.max(0, Math.floor(input.itemCount))
  const itemHeight = Math.max(1, input.itemHeight)
  const buffer = Math.max(0, Math.floor(input.buffer))
  const estimated = Math.max(1, input.estimated ?? itemHeight)
  const heights = input.heights ?? null
  const scrollTop = Math.max(0, input.scrollTop)
  const viewportHeight = Math.max(0, input.viewportHeight)

  /** 前缀和（长度 `count + 1`；第 i 项起点 = `offsets[i]`） */
  const offsets = new Array<number>(count + 1)
  offsets[0] = 0
  for (let i = 0; i < count; i++) {
    offsets[i + 1] = (offsets[i] as number) + (heights?.[i] ?? estimated)
  }

  const totalHeight = offsets[count] ?? 0

  function indexAt(top: number): number {
    if (count === 0) {
      return 0
    }
    if (!heights) {
      return Math.min(count - 1, Math.max(0, Math.floor(top / itemHeight)))
    }
    if (top <= 0) {
      return 0
    }
    if (top >= (offsets[count] as number)) {
      return count - 1
    }
    // 二分：最大 i 使 offsets[i] <= top
    let lo = 0
    let hi = count - 1
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2)
      if ((offsets[mid] as number) <= top) {
        lo = mid
      } else {
        hi = mid - 1
      }
    }
    return lo
  }

  const startIndex = Math.max(0, indexAt(scrollTop) - buffer)
  const bottom = scrollTop + Math.max(viewportHeight, itemHeight)
  const last = indexAt(bottom)
  const endIndex = Math.min(count, last + 1 + buffer)
  const offsetY = offsets[startIndex] ?? 0

  function offsetOf(index: number): number {
    const bounded = Math.min(Math.max(0, index), count)
    return offsets[bounded] ?? 0
  }

  return { startIndex, endIndex, offsetY, totalHeight, offsetOf, indexAt }
}
