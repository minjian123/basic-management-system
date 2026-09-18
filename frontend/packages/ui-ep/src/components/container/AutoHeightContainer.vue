<script setup lang="ts">
// 自适应高度容器：高度占满父剩余空间（按头部 / 工具栏高度扣减）。
import { computed, type CSSProperties } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

interface Props {
  /** 需扣减的高度（数字按 px）。 */
  offset?: number | string
  /** 最小高度。 */
  minHeight?: number | string
}

const props = withDefaults(defineProps<Props>(), { offset: 0, minHeight: undefined })

const { sizeToken, isCompact } = useBaseContainer()

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
  }
})
</script>

<template>
  <div
    class="bms-auto-height-container"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
    :style="style"
  >
    <slot />
  </div>
</template>
