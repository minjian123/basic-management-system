<script setup lang="ts">
// 自适应高度容器：高度占满父剩余空间（按头部 / 工具栏高度扣减）；尺寸变化去抖后通知重算。
import { computed, onBeforeUnmount, onMounted, ref, watch, type CSSProperties } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'
import { debounce, type DebouncedFunction } from '../../utils/debounce'
import { observeResize, supportsResize } from '../../utils/observe'

interface Props {
  /** 需扣减的高度（数字按 px）。 */
  offset?: number | string
  /** 最小高度。 */
  minHeight?: number | string
  /** 最大高度。 */
  maxHeight?: number | string
  /** 内容超出时内部滚动。 */
  scroll?: boolean
  /** 尺寸变化重算的节流时长（毫秒，去抖）。 */
  recalcDelay?: number
}

const props = withDefaults(defineProps<Props>(), {
  offset: 0,
  minHeight: undefined,
  maxHeight: undefined,
  scroll: true,
  recalcDelay: 100,
})

const emit = defineEmits<{ recalc: [payload: { width: number; height: number }] }>()

const { sizeToken, isCompact } = useBaseContainer()
const root = ref<HTMLElement>()

/**
 * 长度归一（数字按 px）。
 *
 * @param value 数字或 CSS 长度。
 * @returns CSS 长度；未提供返回 undefined。
 */
function toLength(value: number | string | undefined): string | undefined {
  if (value === undefined) {
    return undefined
  }
  return typeof value === 'number' ? `${value}px` : value
}

const style = computed<CSSProperties>(() => {
  const offset = toLength(props.offset) ?? '0px'
  return {
    height: offset === '0px' ? '100%' : `calc(100% - ${offset})`,
    minHeight: toLength(props.minHeight),
    maxHeight: toLength(props.maxHeight),
  }
})

/** 派发重算通知（携带当前尺寸）。 */
function notifyRecalc(): void {
  const element = root.value
  emit('recalc', { width: element?.clientWidth ?? 0, height: element?.clientHeight ?? 0 })
}

const debouncedRecalc = ref<DebouncedFunction<[]> | undefined>(undefined)
let offResize: () => void = () => {}

/**
 * 手动触发重算（内容异步变化后由消费方调用）。
 */
function recalculate(): void {
  notifyRecalc()
}

defineExpose({ recalculate })

watch(
  () => props.recalcDelay,
  (delay) => {
    debouncedRecalc.value?.cancel()
    debouncedRecalc.value = debounce(notifyRecalc, delay)
  },
  { immediate: true },
)

onMounted(() => {
  if (root.value !== undefined && supportsResize()) {
    offResize = observeResize(root.value, () => {
      debouncedRecalc.value?.()
    })
  }
})

onBeforeUnmount(() => {
  offResize()
  debouncedRecalc.value?.cancel()
})
</script>

<template>
  <div
    ref="root"
    class="bms-auto-height-container"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
    :data-scroll="scroll || undefined"
    :style="style"
  >
    <slot />
  </div>
</template>

<style scoped>
.bms-auto-height-container {
  box-sizing: border-box;
  min-height: 0;
  overflow: hidden;
}

.bms-auto-height-container[data-scroll] {
  overflow: auto;
}
</style>
