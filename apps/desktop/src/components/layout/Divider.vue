<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
/**
 * 分割线：方向 / 文案位置 / 虚线（《组件设计 · 间距与分割线》）。
 */

import { computed, useAttrs } from 'vue'

import { useComponentBase } from '@/base/useComponentBase'

const props = withDefaults(
  defineProps<{
    direction?: 'horizontal' | 'vertical'
    /** 文案位置（默认插槽文案） */
    contentPosition?: 'left' | 'center' | 'right'
    dashed?: boolean
  }>(),
  { direction: 'horizontal', contentPosition: 'center', dashed: false },
)

const base = useComponentBase({ ns: 'bms', identifier: 'divider' })
const attrs = useAttrs()

const borderStyle = computed(() => (props.dashed ? 'dashed' : 'solid'))

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('divider'), cls], style: sty, ...rest })
})
</script>

<template>
  <el-divider
    v-bind="elAttrs"
    :direction="direction"
    :content-position="contentPosition"
    :border-style="borderStyle"
  >
    <slot />
  </el-divider>
</template>
