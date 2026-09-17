<script setup lang="ts" generic="T extends Record<string, unknown>">
/**
 * 虚拟列表容器（《组件设计 · 虚拟列表容器》）：大数据只渲染可视区 + 缓冲。
 *
 * - 渲染：可视区 + 上 / 下 `buffer` 项，DOM 数量恒定；外层撑高占位、可视区 `translateY` 定位；
 * - 高度：统一前缀和路径（定高 = 估值 `itemHeight` 的特例）；传入 `estimatedHeight` 启用动态模式——
 *   `ResizeObserver` 逐项测量 + 缓存（键 = `keyField`）+ 前缀和重建 + 可视区上方变化 `scrollTop` 补偿；
 *   无 RO 环境退化为更新后 `offsetHeight` 测量；
 * - 触底：scroll 计算（进入阈值一次 / 离开重置）；`scroll` 事件含可视区索引（rAF 合并）；
 * - 方法：`scrollToIndex`（pending：数据未就绪记忆，`items` 更新后定位一次）/ `scrollToTop` /
 *   `scrollToBottom` / `scrollTop` / `el` / `resetMeasurement`；
 * - 建议 ≥1000 条启用（组件不自动降级）；`height: auto` 退化为普通渲染（开发态告警）。
 */

import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  onUpdated,
  ref,
  useAttrs,
  watch,
} from 'vue'

import { useComponentBase } from '@bms/vue'

import { resolveSize } from './size'
import type { VirtualScrollMetrics } from './types'
import { useVirtualRange } from './useVirtualRange'

const props = withDefaults(
  defineProps<{
    /** 数据源 */
    items?: T[]
    /** 定高项高（px） */
    itemHeight?: number
    /** 动态模式估值（px；传入即启用高度测量与缓存） */
    estimatedHeight?: number
    /** 上 / 下缓冲项数 */
    buffer?: number
    /** 项唯一键字段 */
    keyField?: string
    /** 容器高度（数字按 px；虚拟滚动需确定视口，`auto` 退化为普通渲染） */
    height?: number | string
    /** 触底容差（px） */
    threshold?: number
  }>(),
  {
    items: () => [],
    itemHeight: 40,
    estimatedHeight: undefined,
    buffer: 5,
    keyField: 'id',
    height: '100%',
    threshold: 0,
  },
)

const emit = defineEmits<{
  scroll: [metrics: VirtualScrollMetrics]
  'reach-bottom': [metrics: VirtualScrollMetrics]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'virtual-list' })
const attrs = useAttrs()

const bodyRef = ref<HTMLElement | null>(null)
const itemElements = new Map<number, HTMLElement>()
const elementIndex = new WeakMap<Element, number>()
const measureCache = ref<Map<string, number>>(new Map())
let resizeObserver: ResizeObserver | null = null

const list = computed(() => props.items)
const isDynamic = computed(() => props.estimatedHeight !== undefined)
const isAutoHeight = computed(() => props.height === 'auto')
const estimate = computed(() => props.estimatedHeight ?? props.itemHeight)

function keyOf(item: T, index: number): string {
  const value = (item as Record<string, unknown>)[props.keyField]
  return value === undefined || value === null ? `#${index}` : String(value)
}

/** 高度数组（实测缓存 → 估值缺省；只读注入可视区计算） */
const heights = computed<(number | undefined)[]>(() =>
  list.value.map((item, index) => measureCache.value.get(keyOf(item, index))),
)

const range = useVirtualRange({
  itemCount: computed(() => list.value.length),
  itemHeight: computed(() => props.itemHeight),
  buffer: computed(() => props.buffer),
  heights,
  estimated: estimate,
})

const { startIndex, endIndex, offsetY, totalHeight } = range

const visibleItems = computed(() =>
  list.value
    .slice(startIndex.value, endIndex.value)
    .map((item, offset) => ({ item, index: startIndex.value + offset })),
)

const rootStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {}
  const height = resolveSize(props.height)
  if (height) {
    style.height = height
  }
  return style
})

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [
      base.nsClass('virtual-list'),
      !isAutoHeight.value && base.nsClass('virtual-list--styled'),
      cls,
    ],
    style: sty,
    ...rest,
  })
})

function metrics(): VirtualScrollMetrics {
  const body = bodyRef.value
  return {
    scrollTop: body?.scrollTop ?? 0,
    scrollHeight: body?.scrollHeight ?? 0,
    clientHeight: body?.clientHeight ?? 0,
    startIndex: startIndex.value,
    endIndex: endIndex.value,
  }
}

// ===== 测量（动态模式） =====

function applyMeasurement(index: number, height: number): void {
  if (!isDynamic.value) {
    return
  }
  const value = Math.round(height)
  if (value <= 0) {
    return
  }
  const item = list.value[index]
  if (!item) {
    return
  }
  const key = keyOf(item, index)
  const previous = measureCache.value.get(key) ?? estimate.value
  if (previous === value) {
    return
  }
  const next = new Map(measureCache.value)
  next.set(key, value)
  measureCache.value = next
  // 可视区上方（含缓冲项）高度变化 → 补偿 scrollTop（防跳动）
  const viewportStart = range.indexAt(bodyRef.value?.scrollTop ?? 0)
  if (index < viewportStart && bodyRef.value) {
    const delta = value - previous
    void nextTick(() => {
      if (bodyRef.value) {
        bodyRef.value.scrollTop += delta
      }
    })
  }
}

function measureItem(index: number, el: HTMLElement): void {
  if (!isDynamic.value) {
    return
  }
  applyMeasurement(index, el.getBoundingClientRect().height || el.offsetHeight)
}

function registerItem(index: number, el: Element | { $el?: Element } | null): void {
  const htmlEl = (el as { $el?: Element } | null)?.$el ?? (el as HTMLElement | null)
  if (!htmlEl || !(htmlEl instanceof HTMLElement)) {
    return
  }
  itemElements.set(index, htmlEl)
  elementIndex.set(htmlEl, index)
  resizeObserver?.observe(htmlEl)
  measureItem(index, htmlEl)
}

onUpdated(() => {
  if (!isDynamic.value || resizeObserver) {
    return
  }
  // 无 RO 环境：更新后按当前渲染项重新测量（`offsetHeight`）
  itemElements.forEach((el, index) => measureItem(index, el))
})

// ===== 滚动与触底 =====

let rafId: number | null = null
let bottomReached = false

function checkReach(): void {
  const body = bodyRef.value
  if (!body) {
    return
  }
  const margin = Math.max(0, props.threshold)
  if (body.scrollHeight - body.scrollTop - body.clientHeight <= margin) {
    if (!bottomReached) {
      bottomReached = true
      emit('reach-bottom', metrics())
    }
  } else {
    bottomReached = false
  }
}

function onScroll(): void {
  if (rafId !== null) {
    return
  }
  rafId = requestAnimationFrame(() => {
    rafId = null
    const body = bodyRef.value
    if (!body) {
      return
    }
    range.setViewport(body.scrollTop, body.clientHeight)
    checkReach()
    emit('scroll', metrics())
  })
}

// ===== 定位（`scrollToIndex` pending 语义） =====

const pendingIndex = ref<number | null>(null)

function locateIndex(index: number, options?: ScrollToOptions): void {
  const body = bodyRef.value
  if (!body) {
    return
  }
  const top = range.offsetOf(index)
  body.scrollTo({ top, ...options })
  range.setViewport(top, body.clientHeight)
}

function scrollToIndex(index: number, options?: ScrollToOptions): void {
  if (!Number.isFinite(index) || index < 0) {
    return
  }
  if (index >= list.value.length) {
    // 数据未就绪：记忆目标，`items` 更新后定位一次
    pendingIndex.value = index
    return
  }
  locateIndex(index, options)
}

function scrollToTop(options?: ScrollToOptions): void {
  bodyRef.value?.scrollTo({ top: 0, ...options })
}

function scrollToBottom(options?: ScrollToOptions): void {
  const body = bodyRef.value
  if (body) {
    body.scrollTo({ top: body.scrollHeight, ...options })
  }
}

function resetMeasurement(): void {
  measureCache.value = new Map()
}

// ===== 数据变化（key 校验 / pending 定位） =====

const keyWarned = ref(false)

watch(
  () => props.items,
  async () => {
    if (import.meta.env.DEV && !keyWarned.value) {
      const seen = new Set<string>()
      for (const [index, item] of list.value.entries()) {
        const key = keyOf(item, index)
        if (seen.has(key)) {
          keyWarned.value = true
          console.warn(`[VirtualList] keyField '${props.keyField}' 存在重复值：${key}`)
          break
        }
        seen.add(key)
      }
    }
    if (pendingIndex.value !== null) {
      const target = pendingIndex.value
      pendingIndex.value = null
      await nextTick()
      if (target < list.value.length) {
        locateIndex(target)
      }
    }
  },
)

if (import.meta.env.DEV && props.height === 'auto') {
  console.warn('[VirtualList] height="auto" 无法确定视口，虚拟滚动退化为普通渲染')
}

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const index = elementIndex.get(entry.target)
        if (index === undefined) {
          continue
        }
        const blockSize = entry.borderBoxSize?.[0]?.blockSize
        applyMeasurement(index, typeof blockSize === 'number' && blockSize > 0 ? blockSize : (entry.target as HTMLElement).offsetHeight)
      }
    })
    // 首屏渲染的元素在 onMounted 前已完成注册（ref 回调先于挂载钩子）：补观察
    itemElements.forEach((el) => resizeObserver?.observe(el))
  }
  const body = bodyRef.value
  if (body) {
    range.setViewport(body.scrollTop, body.clientHeight)
  }
})

onBeforeUnmount(() => {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
  resizeObserver?.disconnect()
  resizeObserver = null
  itemElements.clear()
})

defineExpose({
  scrollToIndex,
  scrollToTop,
  scrollToBottom,
  resetMeasurement,
  get scrollTop(): number {
    return bodyRef.value?.scrollTop ?? 0
  },
  get el(): HTMLElement | null {
    return bodyRef.value
  },
})
</script>

<template>
  <div ref="bodyRef" v-bind="elAttrs" :class="base.nsClass('virtual-list')" :style="rootStyle" @scroll="onScroll">
    <template v-if="isAutoHeight">
      <div
        v-for="(item, index) in list"
        :key="keyOf(item, index)"
        :class="base.nsClass('virtual-list-item')"
        data-testid="virtual-item"
      >
        <slot :item="item" :index="index" />
      </div>
    </template>
    <template v-else>
      <div :class="base.nsClass('virtual-list-spacer')" :style="{ height: `${totalHeight}px` }">
        <div :class="base.nsClass('virtual-list-viewport')" :style="{ transform: `translateY(${offsetY}px)` }">
          <div
            v-for="entry in visibleItems"
            :key="keyOf(entry.item, entry.index)"
            :ref="(el) => registerItem(entry.index, el as Element | null)"
            :class="base.nsClass('virtual-list-item')"
            data-testid="virtual-item"
          >
            <slot :item="entry.item" :index="entry.index" />
          </div>
        </div>
      </div>
    </template>
    <div v-if="list.length === 0" :class="base.nsClass('virtual-list-empty')" data-testid="virtual-empty">
      <slot name="empty" />
    </div>
  </div>
</template>

<style scoped>
.bms-virtual-list {
  overflow: auto;
  position: relative;
}

.bms-virtual-list--styled {
  scrollbar-width: thin;
  scrollbar-color: var(--bms-scrollbar-thumb) var(--bms-scrollbar-track);
}

.bms-virtual-list--styled::-webkit-scrollbar {
  width: var(--bms-scrollbar-size);
  height: var(--bms-scrollbar-size);
}

.bms-virtual-list--styled::-webkit-scrollbar-thumb {
  background: var(--bms-scrollbar-thumb);
  border-radius: var(--bms-scrollbar-radius);
}

.bms-virtual-list--styled::-webkit-scrollbar-thumb:hover {
  background: var(--bms-scrollbar-thumb-hover);
}

.bms-virtual-list--styled::-webkit-scrollbar-track {
  background: var(--bms-scrollbar-track);
}

@media (max-width: 768px) {
  .bms-virtual-list--styled {
    scrollbar-width: none;
  }

  .bms-virtual-list--styled::-webkit-scrollbar {
    display: none;
  }
}
</style>
