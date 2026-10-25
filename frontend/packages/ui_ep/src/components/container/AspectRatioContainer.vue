<script setup lang="ts">
// 宽高比容器：固定宽高比占位防抖动；`aspect-ratio` 不可用时降级 padding-top 技巧。
import { computed, type CSSProperties } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

/** 内容填充模式。 */
export type AspectRatioFit = 'fill' | 'contain' | 'cover' | 'none'

interface Props {
  /** 宽 / 高（缺省 16/9）。 */
  ratio?: number
  /** 内容填充模式（作用于内层直接媒体元素）。 */
  fit?: AspectRatioFit
  /** 最大宽度（数字按 px）。 */
  maxWidth?: number | string
  /** 最小高度（数字按 px）。 */
  minHeight?: number | string
}

const props = withDefaults(defineProps<Props>(), {
  ratio: 16 / 9,
  fit: 'cover',
  maxWidth: undefined,
  minHeight: undefined,
})

const { sizeToken, isCompact } = useBaseContainer()

const resolvedRatio = computed(() => (Number.isFinite(props.ratio) && props.ratio > 0 ? props.ratio : 16 / 9))

const supportsRatio = computed(
  () => typeof CSS !== 'undefined' && typeof CSS.supports === 'function' && CSS.supports('aspect-ratio', '16 / 9'),
)

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

const outerStyle = computed<CSSProperties>(() => {
  const base: CSSProperties = supportsRatio.value
    ? { aspectRatio: String(resolvedRatio.value) }
    : { position: 'relative', paddingTop: `${(1 / resolvedRatio.value) * 100}%` }
  const maxWidth = toLength(props.maxWidth)
  const minHeight = toLength(props.minHeight)
  if (maxWidth !== undefined) {
    base.maxWidth = maxWidth
  }
  if (minHeight !== undefined) {
    base.minHeight = minHeight
  }
  return base
})

const innerStyle = computed<CSSProperties>(() =>
  supportsRatio.value ? {} : { position: 'absolute', inset: '0' },
)
</script>

<template>
  <div
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
    class="bms-aspect-ratio-container"
    :data-degraded="!supportsRatio"
    :style="outerStyle"
  >
    <div class="bms-aspect-ratio-container__inner" :data-fit="fit" :style="innerStyle">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.bms-aspect-ratio-container {
  position: relative;
  overflow: hidden;
  background: var(--bms-color-bg-page);
  border-radius: var(--bms-radius-sm);
}

.bms-aspect-ratio-container__inner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

/* 填充模式：对直接替换元素（图片 / 视频）生效；非替换内容按居中对齐近似 */
.bms-aspect-ratio-container__inner[data-fit='cover'] > :deep(img),
.bms-aspect-ratio-container__inner[data-fit='cover'] > :deep(video) {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.bms-aspect-ratio-container__inner[data-fit='contain'] > :deep(img),
.bms-aspect-ratio-container__inner[data-fit='contain'] > :deep(video) {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.bms-aspect-ratio-container__inner[data-fit='fill'] > :deep(img),
.bms-aspect-ratio-container__inner[data-fit='fill'] > :deep(video) {
  width: 100%;
  height: 100%;
  object-fit: fill;
}

.bms-aspect-ratio-container__inner[data-fit='none'] > :deep(img),
.bms-aspect-ratio-container__inner[data-fit='none'] > :deep(video) {
  object-fit: none;
}
</style>
