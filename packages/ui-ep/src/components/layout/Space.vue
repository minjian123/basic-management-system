<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
/**
 * 间距：元素间距（方向 / 尺寸 / 换行 / 对齐），尺寸映射令牌刻度（《组件设计 · 间距与分割线》）。
 */

import { computed, useAttrs } from 'vue'

import { ElSpace } from 'element-plus'
import 'element-plus/es/components/space/style/css'

import { useComponentBase } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    direction?: 'horizontal' | 'vertical'
    /** 间距档位（映射令牌：none 0 / small 4 / default 8 / large 16）或显式像素 */
    size?: 'none' | 'small' | 'default' | 'large' | number
    wrap?: boolean
    align?: 'start' | 'end' | 'center' | 'baseline' | 'stretch'
  }>(),
  { direction: 'horizontal', size: 'default', wrap: false, align: 'center' },
)

const SIZE_MAP: Record<'none' | 'small' | 'default' | 'large', number> = {
  none: 0,
  small: 4,
  default: 8,
  large: 16,
}

const base = useComponentBase({ ns: 'bms', identifier: 'space' })
const attrs = useAttrs()

const sizeValue = computed(() =>
  typeof props.size === 'number' ? props.size : SIZE_MAP[props.size],
)

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('space'), cls], style: sty, ...rest })
})
</script>

<template>
  <el-space
    v-bind="elAttrs"
    :direction="direction"
    :size="sizeValue"
    :wrap="wrap"
    :alignment="align"
  >
    <slot />
  </el-space>
</template>
