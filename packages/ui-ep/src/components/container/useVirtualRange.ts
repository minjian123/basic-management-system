/**
 * 虚拟列表可视区计算（容器组件类「虚拟列表容器」）。
 *
 * - 前缀和 + 二分查找：定高为「估值 = `itemHeight`」的特例（统一路径，数值等价）；
 * - 动态高度：由调用方注入高度数组（实测 / 估值混合，只读），滚动与测量变化自动重算；
 * - 纯逻辑（不触 DOM），供 `VirtualList` 与后续虚拟化场景（如通用表格）复用。
 */

import { computed, ref, toValue, type ComputedRef, type MaybeRefOrGetter } from 'vue'

export interface VirtualRangeOptions {
  /** 项数 */
  itemCount: MaybeRefOrGetter<number>
  /** 定高项高（px；估值缺省来源） */
  itemHeight: MaybeRefOrGetter<number>
  /** 上 / 下缓冲项数 */
  buffer: MaybeRefOrGetter<number>
  /** 动态高度数组（只读；`undefined` 项按估值；缺省全部按 `itemHeight`） */
  heights?: MaybeRefOrGetter<(number | undefined)[] | null>
  /** 动态估值（px；缺省 = `itemHeight`） */
  estimated?: MaybeRefOrGetter<number | undefined>
}

export interface VirtualRangeReturn {
  /** 渲染起始索引（含缓冲） */
  readonly startIndex: ComputedRef<number>
  /** 渲染结束索引（不含；slice 语义） */
  readonly endIndex: ComputedRef<number>
  /** 可视区起始项前缀偏移（px；`translateY`） */
  readonly offsetY: ComputedRef<number>
  /** 总高度（px；撑高占位） */
  readonly totalHeight: ComputedRef<number>
  /** 指定索引的前缀偏移（px） */
  offsetOf: (index: number) => number
  /** 指定滚动位置所在项索引（二分 / 公式） */
  indexAt: (top: number) => number
  /** 更新视口（滚动位置与可视高度） */
  setViewport: (scrollTop: number, viewportHeight: number) => void
}

export function useVirtualRange(options: VirtualRangeOptions): VirtualRangeReturn {
  const scrollTop = ref(0)
  const viewportHeight = ref(0)

  const count = computed(() => Math.max(0, Math.floor(toValue(options.itemCount))))
  const itemHeight = computed(() => Math.max(1, toValue(options.itemHeight)))
  const buffer = computed(() => Math.max(0, Math.floor(toValue(options.buffer))))
  const estimated = computed(() => Math.max(1, toValue(options.estimated) ?? itemHeight.value))

  /** 前缀和（长度 `count + 1`；第 i 项起点 = `offsets[i]`） */
  const offsets = computed<number[]>(() => {
    const n = count.value
    const heights = options.heights ? toValue(options.heights) : null
    const fallback = estimated.value
    const arr = new Array<number>(n + 1)
    arr[0] = 0
    for (let i = 0; i < n; i++) {
      arr[i + 1] = arr[i] + (heights?.[i] ?? fallback)
    }
    return arr
  })

  const totalHeight = computed(() => offsets.value[count.value] ?? 0)

  function indexAt(top: number): number {
    const n = count.value
    if (n === 0) {
      return 0
    }
    const offs = offsets.value
    if (!options.heights) {
      return Math.min(n - 1, Math.max(0, Math.floor(top / itemHeight.value)))
    }
    if (top <= 0) {
      return 0
    }
    if (top >= offs[n]) {
      return n - 1
    }
    // 二分：最大 i 使 offsets[i] <= top
    let lo = 0
    let hi = n - 1
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2)
      if ((offs[mid] as number) <= top) {
        lo = mid
      } else {
        hi = mid - 1
      }
    }
    return lo
  }

  const startIndex = computed(() => Math.max(0, indexAt(scrollTop.value) - buffer.value))

  const endIndex = computed(() => {
    const bottom = scrollTop.value + Math.max(viewportHeight.value, itemHeight.value)
    const last = indexAt(bottom)
    return Math.min(count.value, last + 1 + buffer.value)
  })

  const offsetY = computed(() => offsets.value[startIndex.value] ?? 0)

  function offsetOf(index: number): number {
    const n = count.value
    const i = Math.min(Math.max(0, index), n)
    return offsets.value[i] ?? 0
  }

  function setViewport(nextScrollTop: number, nextViewportHeight: number): void {
    scrollTop.value = Math.max(0, nextScrollTop)
    viewportHeight.value = Math.max(0, nextViewportHeight)
  }

  return {
    startIndex,
    endIndex,
    offsetY,
    totalHeight,
    offsetOf,
    indexAt,
    setViewport,
  }
}
