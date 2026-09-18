<script setup lang="ts">
// 宽高比容器：固定宽高比占位防抖动；`aspect-ratio` 不可用时降级 padding-top 技巧。
import { computed, type CSSProperties } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

interface Props {
  /** 宽 / 高（缺省 16/9）。 */
  ratio?: number
}

const props = withDefaults(defineProps<Props>(), { ratio: 16 / 9 })

const { sizeToken, isCompact } = useBaseContainer()

const resolvedRatio = computed(() => (Number.isFinite(props.ratio) && props.ratio > 0 ? props.ratio : 16 / 9))

const supportsRatio = computed(
  () => typeof CSS !== 'undefined' && typeof CSS.supports === 'function' && CSS.supports('aspect-ratio', '16 / 9'),
)

const outerStyle = computed<CSSProperties>(() =>
  supportsRatio.value
    ? { aspectRatio: String(resolvedRatio.value) }
    : { position: 'relative', paddingTop: `${(1 / resolvedRatio.value) * 100}%` },
)

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
    <div class="bms-aspect-ratio-container__inner" :style="innerStyle">
      <slot />
    </div>
  </div>
</template>
