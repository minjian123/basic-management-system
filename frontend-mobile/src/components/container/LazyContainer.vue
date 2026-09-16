<script setup lang="ts">
/**
 * 懒加载容器（《组件设计 · 懒加载容器》）：内容进入视口才渲染。
 *
 * - 触发：IntersectionObserver（`rootMargin` 提前量）；
 * - 占位：默认内置轻量骨架（双端同款、无跨域依赖；`#placeholder` 插槽可传 `SkeletonBlock` 等正式件）；
 *   未渲染占位高度经 `minHeight`，缺省由样式覆盖点 `--bms-lazy-min-height` 控制（可全局覆盖）；
 * - 缓存：`once=true` 渲染后不卸载；`once=false` + `unmountOnLeave` 离开视口卸载（状态丢失）；
 * - 降级：IO 不可用（SSR / 旧环境）直接渲染。
 */

import { computed, onBeforeUnmount, onMounted, ref, useAttrs, watch } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

import { resolveSize } from './size'

const props = withDefaults(
  defineProps<{
    /** 未渲染占位最小高度（数字按 px）；缺省由 `--bms-lazy-min-height` 控制 */
    minHeight?: number | string
    /** 提前触发的视口边距（IO `rootMargin`） */
    rootMargin?: string
    /** 只渲染一次（渲染后不卸载） */
    once?: boolean
    /** 离开视口卸载（仅 `once=false` 生效） */
    unmountOnLeave?: boolean
  }>(),
  {
    minHeight: undefined,
    rootMargin: '100px',
    once: true,
    unmountOnLeave: false,
  },
)

const base = useComponentBase({ ns: 'bms', identifier: 'lazy-container' })
const attrs = useAttrs()

const rootRef = ref<HTMLElement | null>(null)
/** 是否已显示（无 IO 环境直接显示） */
const shown = ref(typeof IntersectionObserver === 'undefined')
let observer: IntersectionObserver | null = null

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('lazy-container'), cls],
    style: sty,
    ...rest,
  })
})

const placeholderStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {}
  const minHeight = resolveSize(props.minHeight)
  if (minHeight) {
    style.minHeight = minHeight
  }
  return style
})

function onIntersect(entries: IntersectionObserverEntry[]): void {
  const entry = entries[0]
  if (!entry) {
    return
  }
  if (entry.isIntersecting) {
    shown.value = true
    if (props.once) {
      observer?.disconnect()
      observer = null
    }
  } else if (!props.once && props.unmountOnLeave) {
    shown.value = false
  }
}

function setupObserver(): void {
  if (typeof IntersectionObserver === 'undefined' || !rootRef.value || observer) {
    return
  }
  observer = new IntersectionObserver(onIntersect, { rootMargin: props.rootMargin })
  observer.observe(rootRef.value)
}

if (import.meta.env.DEV && props.unmountOnLeave && props.once) {
  console.warn('[LazyContainer] unmountOnLeave 仅在 once=false 时生效（已忽略）')
}

onMounted(setupObserver)

watch(
  () => props.rootMargin,
  () => {
    if (observer) {
      observer.disconnect()
      observer = null
    }
    setupObserver()
  },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <div ref="rootRef" v-bind="elAttrs" :class="base.nsClass('lazy-container')">
    <template v-if="shown">
      <slot />
    </template>
    <div
      v-else
      :class="base.nsClass('lazy-container-placeholder')"
      :style="placeholderStyle"
      data-testid="lazy-placeholder"
    >
      <slot name="placeholder">
        <div :class="base.nsClass('lazy-container-skeleton')" aria-hidden="true" />
      </slot>
    </div>
  </div>
</template>

<style scoped>
.bms-lazy-container-placeholder {
  /* 缺省占位高度覆盖点（未登记为正式令牌；消费方可全局覆盖） */
  min-height: var(--bms-lazy-min-height, auto);
}

.bms-lazy-container-skeleton {
  width: 100%;
  min-height: 80px;
  border-radius: var(--bms-radius-sm);
  background: linear-gradient(
    90deg,
    var(--bms-color-bg-page) 25%,
    var(--bms-color-border) 37%,
    var(--bms-color-bg-page) 63%
  );
  background-size: 400% 100%;
  animation: bms-lazy-skeleton-loading 1.4s ease infinite;
}

@keyframes bms-lazy-skeleton-loading {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}
</style>
