<script setup lang="ts">
// 可调分栏：指针拖拽 + 键盘微调 + 双击复位；轻量自研，不引入第三方。
import { computed, onBeforeUnmount, ref, watch, type CSSProperties } from 'vue'

import { useBaseLayout } from '../../composables/useBaseLayout'
import { startPointerDrag } from '../../utils/keyboard'


/** 分割方向。 */
export type SplitDirection = 'horizontal' | 'vertical'

const DEFAULT_SIZE = 280

interface Props {
  /** 首区尺寸（px）。 */
  modelValue?: number
  /** 最小尺寸。 */
  min?: number
  /** 最大尺寸。 */
  max?: number
  /** 方向。 */
  direction?: SplitDirection
  /** 是否禁用拖拽。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  min: 180,
  max: undefined,
  direction: 'horizontal',
  disabled: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: number]; 'resize-end': [value: number] }>()

const container = ref<HTMLElement>()
const dragging = ref(false)
const size = ref(props.modelValue ?? DEFAULT_SIZE)

watch(
  () => props.modelValue,
  (value) => {
    if (value !== undefined && value !== size.value) {
      size.value = value
    }
  },
)

const { hidden } = useBaseLayout({ gap: size.value })
const firstStyle = computed<CSSProperties>(() =>
  props.direction === 'horizontal' ? { width: `${size.value}px` } : { height: `${size.value}px` },
)

function bounds(): { min: number; max: number } {
  const measured = props.direction === 'horizontal' ? container.value?.clientWidth : container.value?.clientHeight
  const min = Math.max(0, props.min)
  const hardMax = props.max ?? Number.POSITIVE_INFINITY
  const softMax = measured !== undefined && measured > 0 ? measured : hardMax
  return { min, max: Math.max(min, Math.min(hardMax, softMax)) }
}

function clamp(value: number): number {
  const { min, max } = bounds()
  return Math.min(Math.max(value, min), max)
}

function apply(next: number): void {
  size.value = clamp(next)
  emit('update:modelValue', size.value)
}

function pointerPosition(event: Event): number {
  const source = event as MouseEvent
  return props.direction === 'horizontal' ? source.clientX : source.clientY
}

let startPosition = 0
let startSize = 0
let cancelDrag: (() => void) | undefined

function onPointerMove(event: Event): void {
  apply(startSize + (pointerPosition(event) - startPosition))
}

function onPointerDown(event: Event): void {
  if (props.disabled) {
    return
  }
  dragging.value = true
  startPosition = pointerPosition(event)
  startSize = size.value
  cancelDrag = startPointerDrag(onPointerMove, () => {
    if (!dragging.value) {
      return
    }
    dragging.value = false
    cancelDrag = undefined
    emit('resize-end', size.value)
  })
}

function onKeydown(event: KeyboardEvent): void {
  if (props.disabled) {
    return
  }
  const step = 10
  const decrease = props.direction === 'horizontal' ? 'ArrowLeft' : 'ArrowUp'
  const increase = props.direction === 'horizontal' ? 'ArrowRight' : 'ArrowDown'
  if (event.key === decrease) {
    event.preventDefault()
    apply(size.value - step)
  } else if (event.key === increase) {
    event.preventDefault()
    apply(size.value + step)
  }
}

function onDblclick(): void {
  if (props.disabled) {
    return
  }
  apply(props.modelValue ?? DEFAULT_SIZE)
}

onBeforeUnmount(() => {
  cancelDrag?.()
})
</script>

<template>
  <div
    v-show="!hidden"
    ref="container"
    class="bms-split-pane"
    :class="{ 'is-dragging': dragging }"
    :data-direction="direction"
  >
    <div class="bms-split-pane__first" :style="firstStyle">
      <slot name="first" />
    </div>
    <div
      class="bms-split-pane__handle"
      data-test="split-handle"
      role="separator"
      tabindex="0"
      :aria-valuenow="size"
      @pointerdown="onPointerDown"
      @keydown="onKeydown"
      @dblclick="onDblclick"
    />
    <div class="bms-split-pane__second">
      <slot />
    </div>
  </div>
</template>
