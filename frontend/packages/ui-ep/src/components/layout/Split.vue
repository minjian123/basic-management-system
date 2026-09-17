<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
/**
 * 分栏：可拖拽的左右 / 上下分割布局（《组件设计 · 分栏》）。
 *
 * 拖拽过程轻量（CSS 变量 / 百分比宽度），`resize-end` 才持久化（`usePersistedState`）；
 * 窄屏（< md）自动转单栏；`min`（px）/ `max`（比例）限位。
 */

import { computed, onBeforeUnmount, onMounted, ref, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'
import { usePersistedState } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    direction?: 'horizontal' | 'vertical'
    /** 初始比例（0 ~ 1） */
    defaultRatio?: number
    /** 首侧最小尺寸（px） */
    min?: number
    /** 首侧最大比例（0 ~ 1） */
    max?: number
    collapsible?: boolean
    /** 比例持久化键（用户偏好；缺省不持久化） */
    storageKey?: string
  }>(),
  { direction: 'horizontal', defaultRatio: 0.5, min: 120, max: 0.7, collapsible: false, storageKey: '' },
)

const emit = defineEmits<{
  resize: [ratio: number]
  'resize-end': [ratio: number]
  'collapse-change': [collapsed: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'split' })
const attrs = useAttrs()

const persistKey = props.storageKey.trim()
const ratioStore = persistKey
  ? usePersistedState<number>({ key: `${persistKey}:ratio`, defaultValue: props.defaultRatio })
  : null

function clamp(value: number): number {
  if (!Number.isFinite(value)) {
    return props.defaultRatio
  }
  return Math.min(props.max, Math.max(0.05, value))
}

const ratio = ref(clamp((ratioStore?.get() as number | undefined) ?? props.defaultRatio))
const collapsed = ref(false)
const dragging = ref(false)
const containerRef = ref<HTMLElement | null>(null)
const isNarrow = ref(false)
let mql: MediaQueryList | null = null

function onMqlChange(event: MediaQueryListEvent): void {
  isNarrow.value = event.matches
}

onMounted(() => {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    mql = window.matchMedia('(max-width: 767px)')
    isNarrow.value = mql.matches
    mql.addEventListener('change', onMqlChange)
  }
})

onBeforeUnmount(() => {
  mql?.removeEventListener('change', onMqlChange)
})

const horizontal = computed(() => props.direction === 'horizontal' && !isNarrow.value)

const firstStyle = computed(() => {
  if (collapsed.value) {
    return horizontal.value ? { width: '0px' } : { height: '0px' }
  }
  const size = `${Math.round(ratio.value * 100)}%`
  return horizontal.value ? { width: size } : { height: size }
})

function onSplitterDown(event: PointerEvent): void {
  dragging.value = true
  ;(event.target as HTMLElement).setPointerCapture?.(event.pointerId)
}

function onSplitterMove(event: PointerEvent): void {
  if (!dragging.value) {
    return
  }
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect) {
    return
  }
  const total = horizontal.value ? rect.width : rect.height
  if (total === 0) {
    return
  }
  const offset = horizontal.value ? event.clientX - rect.left : event.clientY - rect.top
  ratio.value = clamp(offset / total)
  emit('resize', ratio.value)
}

function onSplitterUp(event: PointerEvent): void {
  if (!dragging.value) {
    return
  }
  dragging.value = false
  ;(event.target as HTMLElement).releasePointerCapture?.(event.pointerId)
  ratioStore?.set(ratio.value)
  emit('resize-end', ratio.value)
}

function toggleCollapse(): void {
  collapsed.value = !collapsed.value
  emit('collapse-change', collapsed.value)
}

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [
      base.nsClass('split'),
      horizontal.value ? 'bms-split--horizontal' : 'bms-split--vertical',
      cls,
    ],
    style: sty,
    ...rest,
  })
})

defineExpose({
  reset: () => {
    ratio.value = clamp(props.defaultRatio)
    ratioStore?.set(ratio.value)
  },
})
</script>

<template>
  <div ref="containerRef" v-bind="elAttrs" :class="base.nsClass('split')">
    <div :class="base.nsClass('split-first')" :style="firstStyle">
      <slot name="first" />
    </div>

    <div
      :class="[base.nsClass('split-splitter'), dragging && 'is-dragging']"
      role="separator"
      @pointerdown="onSplitterDown"
      @pointermove="onSplitterMove"
      @pointerup="onSplitterUp"
      @pointercancel="onSplitterUp"
    >
      <button
        v-if="collapsible && !collapsed"
        type="button"
        :class="base.nsClass('split-collapse')"
        @click="toggleCollapse"
      >
        ‹
      </button>
    </div>

    <div v-if="collapsed && collapsible" :class="base.nsClass('split-expand-bar')">
      <button type="button" :class="base.nsClass('split-collapse')" @click="toggleCollapse">›</button>
    </div>

    <div :class="base.nsClass('split-second')">
      <slot name="second" />
    </div>
  </div>
</template>

<style scoped>
.bms-split {
  display: flex;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
}

.bms-split--vertical {
  flex-direction: column;
}

.bms-split-first {
  flex: none;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

.bms-split-second {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

.bms-split-splitter {
  position: relative;
  flex: none;
  background: var(--bms-color-border);
}

.bms-split--horizontal > .bms-split-splitter {
  width: 5px;
  cursor: col-resize;
}

.bms-split--vertical > .bms-split-splitter {
  height: 5px;
  cursor: row-resize;
}

.bms-split-splitter:hover,
.bms-split-splitter.is-dragging {
  background: var(--bms-color-primary);
  opacity: 0.5;
}

.bms-split-collapse {
  position: absolute;
  top: 50%;
  left: 50%;
  padding: 2px 4px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  line-height: 1;
  transform: translate(-50%, -50%);
  cursor: pointer;
}

.bms-split-expand-bar {
  display: flex;
  flex: none;
  align-items: center;
  padding: 0 2px;
  background: var(--bms-color-bg-page);
}
</style>
