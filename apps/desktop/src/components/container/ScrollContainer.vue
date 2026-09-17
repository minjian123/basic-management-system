<script setup lang="ts">
/**
 * 滚动容器（《组件设计 · 滚动容器》）：统一滚动区。
 *
 * - 高度：`height` / `maxHeight`（数字按 px，字符串原样，`auto` 内容撑开）；
 * - 滚动条：默认 CSS 样式化（消费 `--bms-scrollbar-*` 令牌；移动端隐藏自绘），`nativeScrollbar` 用系统默认；
 * - 触底 / 触顶：IntersectionObserver 哨兵（`threshold` 为预提前量）；IO 不可用降级 scroll 计算；
 *   进入阈值触发一次，离开后重置（防重复触发）；
 * - 位置保持：`keepPosition` + `positionKey`（缺省实例 uid）经 `scrollPosition.ts` 读写；
 * - 插槽：`header` / `footer` 固定不滚动，默认插槽为滚动区；暴露 `scrollTo*` / `scrollTop` / `el`。
 */

import {
  computed,
  getCurrentInstance,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  useAttrs,
  watch,
} from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

import { createScrollPositionStore } from './scrollPosition'
import { resolveSize } from './size'
import type { ScrollMetrics } from './types'

const props = withDefaults(
  defineProps<{
    /** 高度（数字按 px；字符串原样，`auto` 内容撑开） */
    height?: number | string
    /** 最大高度（解析同 `height`） */
    maxHeight?: number | string
    /** 使用系统滚动条（不加样式化类） */
    nativeScrollbar?: boolean
    /** 保持滚动位置（切换 / 重挂载恢复） */
    keepPosition?: boolean
    /** 位置键（标签键 / 路由 name 等）；缺省用实例 uid（仅当前挂载生命周期） */
    positionKey?: string
    /** 滚动事件节流（ms；`0` 不节流） */
    throttle?: number
    /** 触底 / 触顶阈值（px）：IO 预提前量与 scroll 计算容差共用 */
    threshold?: number
  }>(),
  {
    height: undefined,
    maxHeight: undefined,
    nativeScrollbar: false,
    keepPosition: false,
    positionKey: undefined,
    throttle: 100,
    threshold: 0,
  },
)

const emit = defineEmits<{
  scroll: [metrics: ScrollMetrics]
  'reach-bottom': [metrics: ScrollMetrics]
  'reach-top': [metrics: ScrollMetrics]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'scroll-container' })
const attrs = useAttrs()

const bodyRef = ref<HTMLElement | null>(null)
const topSentinelRef = ref<HTMLElement | null>(null)
const bottomSentinelRef = ref<HTMLElement | null>(null)

const store = createScrollPositionStore()
const instance = getCurrentInstance()
const fallbackKey = `uid:${instance?.uid ?? 0}`
const positionKey = computed(() => props.positionKey ?? fallbackKey)

const bodyStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {}
  const height = resolveSize(props.height)
  const maxHeight = resolveSize(props.maxHeight)
  if (height) {
    style.height = height
  }
  if (maxHeight) {
    style['max-height'] = maxHeight
  }
  return style
})

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('scroll-container'), cls],
    style: sty,
    ...rest,
  })
})

/** 当前滚动度量 */
function metrics(): ScrollMetrics {
  const body = bodyRef.value
  if (!body) {
    return { scrollTop: 0, scrollHeight: 0, clientHeight: 0 }
  }
  return {
    scrollTop: body.scrollTop,
    scrollHeight: body.scrollHeight,
    clientHeight: body.clientHeight,
  }
}

/** 有效阈值（px） */
const margin = computed(() => Math.max(0, props.threshold))

// ===== 触底 / 触顶：IO 哨兵（进入一次 / 离开重置）+ scroll 降级 =====

const hasIO = typeof IntersectionObserver !== 'undefined'
let observer: IntersectionObserver | null = null
let bottomReached = false
let topReached = false

function fireReachBottom(): void {
  if (bottomReached) {
    return
  }
  bottomReached = true
  emit('reach-bottom', metrics())
}

function fireReachTop(): void {
  if (topReached) {
    return
  }
  topReached = true
  emit('reach-top', metrics())
}

/** IO 不可用时的 scroll 计算路径（含离开重置） */
function checkReachByScroll(): void {
  if (hasIO) {
    return
  }
  const { scrollTop, scrollHeight, clientHeight } = metrics()
  if (scrollHeight - scrollTop - clientHeight <= margin.value) {
    fireReachBottom()
  } else {
    bottomReached = false
  }
  if (scrollTop <= margin.value) {
    fireReachTop()
  } else {
    topReached = false
  }
}

function setupObserver(): void {
  if (!hasIO || !bodyRef.value || observer) {
    return
  }
  const body = bodyRef.value
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const isBottom = entry.target === bottomSentinelRef.value
        if (entry.isIntersecting) {
          if (isBottom) {
            fireReachBottom()
          } else {
            fireReachTop()
          }
        } else if (isBottom) {
          bottomReached = false
        } else {
          topReached = false
        }
      }
    },
    {
      root: body,
      rootMargin: `${margin.value}px 0px ${margin.value}px 0px`,
      threshold: 0,
    },
  )
  if (topSentinelRef.value) {
    observer.observe(topSentinelRef.value)
  }
  if (bottomSentinelRef.value) {
    observer.observe(bottomSentinelRef.value)
  }
}

// ===== 滚动事件（leading + trailing 节流） =====

let lastFireAt = 0
let trailingTimer: ReturnType<typeof setTimeout> | null = null

function emitScroll(): void {
  emit('scroll', metrics())
}

function onScroll(): void {
  const throttle = Math.max(0, props.throttle)
  if (throttle === 0) {
    emitScroll()
  } else {
    const now = Date.now()
    const elapsed = now - lastFireAt
    if (elapsed >= throttle) {
      lastFireAt = now
      emitScroll()
    } else if (trailingTimer === null) {
      trailingTimer = setTimeout(() => {
        trailingTimer = null
        lastFireAt = Date.now()
        emitScroll()
      }, throttle - elapsed)
    }
  }
  checkReachByScroll()
  if (props.keepPosition) {
    store.set(positionKey.value, metrics().scrollTop)
  }
}

// ===== 位置保持 =====

function restorePosition(): void {
  const body = bodyRef.value
  if (!props.keepPosition || !body) {
    return
  }
  const saved = store.get(positionKey.value)
  if (saved === undefined) {
    return
  }
  body.scrollTop = saved
  // 内容异步渲染（高度未就绪）时重试一次
  requestAnimationFrame(() => {
    if (bodyRef.value && bodyRef.value.scrollHeight > bodyRef.value.clientHeight) {
      bodyRef.value.scrollTop = saved
    }
  })
}

onMounted(() => {
  setupObserver()
  void nextTick(restorePosition)
})

watch(positionKey, (_next, prev) => {
  if (props.keepPosition && bodyRef.value) {
    store.set(prev, bodyRef.value.scrollTop)
  }
  void nextTick(restorePosition)
})

onBeforeUnmount(() => {
  if (props.keepPosition && bodyRef.value) {
    store.set(positionKey.value, bodyRef.value.scrollTop)
  }
  observer?.disconnect()
  observer = null
  if (trailingTimer !== null) {
    clearTimeout(trailingTimer)
    trailingTimer = null
  }
})

defineExpose({
  /** 定位滚动（`options` 透传原生 `scrollTo`，可 `behavior: 'smooth'`） */
  scrollTo: (top: number, options?: ScrollToOptions): void => {
    bodyRef.value?.scrollTo({ top, ...options })
  },
  /** 回到顶部 */
  scrollToTop: (options?: ScrollToOptions): void => {
    bodyRef.value?.scrollTo({ top: 0, ...options })
  },
  /** 到底部 */
  scrollToBottom: (options?: ScrollToOptions): void => {
    const body = bodyRef.value
    if (body) {
      body.scrollTo({ top: body.scrollHeight, ...options })
    }
  },
  /** 当前滚动位置 */
  get scrollTop(): number {
    return bodyRef.value?.scrollTop ?? 0
  },
  /** 滚动容器元素（原始句柄） */
  get el(): HTMLElement | null {
    return bodyRef.value
  },
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('scroll-container')">
    <div v-if="$slots.header" :class="base.nsClass('scroll-container-header')">
      <slot name="header" />
    </div>

    <div
      ref="bodyRef"
      :class="[
        base.nsClass('scroll-container-body'),
        !nativeScrollbar && base.nsClass('scroll-container--styled'),
      ]"
      :style="bodyStyle"
      tabindex="0"
      @scroll="onScroll"
    >
      <div
        ref="topSentinelRef"
        :class="base.nsClass('scroll-container-sentinel')"
        aria-hidden="true"
      />
      <slot />
      <div
        ref="bottomSentinelRef"
        :class="base.nsClass('scroll-container-sentinel')"
        aria-hidden="true"
      />
    </div>

    <div v-if="$slots.footer" :class="base.nsClass('scroll-container-footer')">
      <slot name="footer" />
    </div>
  </div>
</template>

<style scoped>
.bms-scroll-container {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.bms-scroll-container-header,
.bms-scroll-container-footer {
  flex: none;
}

.bms-scroll-container-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.bms-scroll-container-body.bms-scroll-container--styled {
  scrollbar-width: thin;
  scrollbar-color: var(--bms-scrollbar-thumb) var(--bms-scrollbar-track);
}

.bms-scroll-container-body.bms-scroll-container--styled::-webkit-scrollbar {
  width: var(--bms-scrollbar-size);
  height: var(--bms-scrollbar-size);
}

.bms-scroll-container-body.bms-scroll-container--styled::-webkit-scrollbar-thumb {
  background: var(--bms-scrollbar-thumb);
  border-radius: var(--bms-scrollbar-radius);
}

.bms-scroll-container-body.bms-scroll-container--styled::-webkit-scrollbar-thumb:hover {
  background: var(--bms-scrollbar-thumb-hover);
}

.bms-scroll-container-body.bms-scroll-container--styled::-webkit-scrollbar-track {
  background: var(--bms-scrollbar-track);
}

.bms-scroll-container-sentinel {
  width: 1px;
  height: 1px;
  visibility: hidden;
}

/* 移动端：隐藏自绘滚动条（触屏原生手势滚动） */
@media (max-width: 768px) {
  .bms-scroll-container-body.bms-scroll-container--styled {
    scrollbar-width: none;
  }

  .bms-scroll-container-body.bms-scroll-container--styled::-webkit-scrollbar {
    display: none;
  }
}
</style>
