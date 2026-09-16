<script setup lang="ts">
/**
 * 自适应高度容器（《组件设计 · 自适应高度容器》）：高度占满父容器剩余空间。
 *
 * - 计算：`父元素 clientHeight − offset`（父高不可测 / 无父回退窗口视口高）；`minHeight` / `maxHeight` 裁剪；
 * - 重算：`ResizeObserver` 观察父元素（无 RO 回退 `window.resize`）+ `resizeDebounce` 去抖；
 *   写样式前**值比较**（同值不写，防循环触发）；
 * - 时序：挂载后 `rAF` 重算一次（防 0 高度）；`offset` / 限制变更即时重算；
 * - `scroll=true` 内容超出时内部滚动（消费 `--bms-scrollbar-*` 令牌）。
 */

import { computed, onBeforeUnmount, onMounted, ref, useAttrs, watch } from 'vue'

import { useComponentBase } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    /** 需扣除的高度（头部 / 工具栏 / 边距，px） */
    offset?: number
    /** 最小高度（px） */
    minHeight?: number
    /** 最大高度（px） */
    maxHeight?: number
    /** 内容超出时内部滚动 */
    scroll?: boolean
    /** 重算去抖（ms） */
    resizeDebounce?: number
  }>(),
  {
    offset: 0,
    minHeight: undefined,
    maxHeight: undefined,
    scroll: true,
    resizeDebounce: 100,
  },
)

const base = useComponentBase({ ns: 'bms', identifier: 'auto-height' })
const attrs = useAttrs()

const rootRef = ref<HTMLElement | null>(null)
const height = ref<number | null>(null)
let observer: ResizeObserver | null = null
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('auto-height'), props.scroll && base.nsClass('auto-height--scroll'), cls],
    style: sty,
    ...rest,
  })
})

const rootStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {}
  if (height.value !== null) {
    style.height = `${height.value}px`
  }
  return style
})

function computeHeight(): number {
  const parent = rootRef.value?.parentElement
  const raw = parent?.clientHeight || (typeof window === 'undefined' ? 0 : window.innerHeight)
  let next = raw - props.offset
  if (props.minHeight !== undefined) {
    next = Math.max(next, props.minHeight)
  }
  if (props.maxHeight !== undefined) {
    next = Math.min(next, props.maxHeight)
  }
  return Math.max(0, Math.round(next))
}

function applyHeight(): void {
  const next = computeHeight()
  if (height.value === next) {
    return
  }
  height.value = next
}

function recalculate(): void {
  applyHeight()
}

function scheduleRecalculate(): void {
  if (debounceTimer !== null) {
    clearTimeout(debounceTimer)
  }
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    applyHeight()
  }, Math.max(0, props.resizeDebounce))
}

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(() => scheduleRecalculate())
    const parent = rootRef.value?.parentElement
    if (parent) {
      observer.observe(parent)
    }
  } else if (typeof window !== 'undefined') {
    window.addEventListener('resize', scheduleRecalculate)
  }
  // 挂载后重算一次（防 0 高度）
  requestAnimationFrame(() => applyHeight())
})

watch(
  () => [props.offset, props.minHeight, props.maxHeight],
  () => applyHeight(),
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', scheduleRecalculate)
  }
  if (debounceTimer !== null) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
})

defineExpose({
  recalculate,
  get height(): number {
    return height.value ?? 0
  },
  get el(): HTMLElement | null {
    return rootRef.value
  },
})
</script>

<template>
  <div ref="rootRef" v-bind="elAttrs" :class="base.nsClass('auto-height')" :style="rootStyle">
    <slot />
  </div>
</template>

<style scoped>
.bms-auto-height {
  min-height: 0;
}

.bms-auto-height--scroll {
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--bms-scrollbar-thumb) var(--bms-scrollbar-track);
}

.bms-auto-height--scroll::-webkit-scrollbar {
  width: var(--bms-scrollbar-size);
  height: var(--bms-scrollbar-size);
}

.bms-auto-height--scroll::-webkit-scrollbar-thumb {
  background: var(--bms-scrollbar-thumb);
  border-radius: var(--bms-scrollbar-radius);
}

.bms-auto-height--scroll::-webkit-scrollbar-thumb:hover {
  background: var(--bms-scrollbar-thumb-hover);
}

.bms-auto-height--scroll::-webkit-scrollbar-track {
  background: var(--bms-scrollbar-track);
}

@media (max-width: 768px) {
  .bms-auto-height--scroll {
    scrollbar-width: none;
  }

  .bms-auto-height--scroll::-webkit-scrollbar {
    display: none;
  }
}
</style>
