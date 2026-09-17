/**
 * 可视区投影（Vue 绑定插件）：核心 `computeVirtualRange` ↔ Vue。
 *
 * 接口面与旧件（`ui-ep` 内 `useVirtualRange`）同构：`MaybeRefOrGetter` 入参、
 * `ComputedRef` 出参；纯逻辑单份在 `@bms/core`，本文件只做响应式桥接。
 */

import { computed, ref, toValue, type ComputedRef, type MaybeRefOrGetter } from 'vue'

import { computeVirtualRange } from '@bms/core'

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

  const result = computed(() =>
    computeVirtualRange({
      itemCount: toValue(options.itemCount),
      itemHeight: toValue(options.itemHeight),
      buffer: toValue(options.buffer),
      // 选项在场（含取值 `null`）即走动态路径（与旧件判定一致）
      heights: options.heights ? (toValue(options.heights) ?? []) : null,
      estimated: toValue(options.estimated),
      scrollTop: scrollTop.value,
      viewportHeight: viewportHeight.value,
    }),
  )

  function setViewport(nextScrollTop: number, nextViewportHeight: number): void {
    scrollTop.value = Math.max(0, nextScrollTop)
    viewportHeight.value = Math.max(0, nextViewportHeight)
  }

  return {
    startIndex: computed(() => result.value.startIndex),
    endIndex: computed(() => result.value.endIndex),
    offsetY: computed(() => result.value.offsetY),
    totalHeight: computed(() => result.value.totalHeight),
    offsetOf: (index) => result.value.offsetOf(index),
    indexAt: (top) => result.value.indexAt(top),
    setViewport,
  }
}
