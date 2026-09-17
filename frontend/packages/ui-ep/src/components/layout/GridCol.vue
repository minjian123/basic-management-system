<script setup lang="ts">
/**
 * 栅格列：24 栅格跨度与偏移、响应式断点（《组件设计 · 栅格》）。
 */

import { computed, useAttrs } from 'vue'

import { ElCol } from 'element-plus'
import 'element-plus/es/components/col/style/css'

import { useComponentBase } from '@bms/vue'

withDefaults(
  defineProps<{
    /** 跨度（0 ~ 24） */
    span?: number
    /** 偏移（0 ~ 24） */
    offset?: number
    /** 响应式断点跨度（与 `useLayout` 断点一致） */
    xs?: number
    sm?: number
    md?: number
    lg?: number
    xl?: number
  }>(),
  { span: 24, offset: 0, xs: undefined, sm: undefined, md: undefined, lg: undefined, xl: undefined },
)

const base = useComponentBase({ ns: 'bms', identifier: 'grid-col' })
const attrs = useAttrs()

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('grid-col'), cls], style: sty, ...rest })
})
</script>

<template>
  <el-col
    v-bind="elAttrs"
    :span="span"
    :offset="offset"
    :xs="xs"
    :sm="sm"
    :md="md"
    :lg="lg"
    :xl="xl"
  >
    <slot />
  </el-col>
</template>
