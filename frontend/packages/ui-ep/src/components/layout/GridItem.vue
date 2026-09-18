<script setup lang="ts">
// 栅格子项：`el-col` 薄封装，支持响应式断点。
import { ElCol } from 'element-plus'

import { useBaseLayout } from '../../composables/useBaseLayout'

interface Props {
  /** 列宽（24 栅）。 */
  span?: number
  /** 左侧偏距。 */
  offset?: number
  /** 超小屏列宽。 */
  xs?: number
  /** 小屏列宽。 */
  sm?: number
  /** 中屏列宽。 */
  md?: number
  /** 大屏列宽。 */
  lg?: number
  /** 超大屏列宽。 */
  xl?: number
}

withDefaults(defineProps<Props>(), {
  span: 24,
  offset: 0,
  xs: undefined,
  sm: undefined,
  md: undefined,
  lg: undefined,
  xl: undefined,
})

const { hidden } = useBaseLayout()
</script>

<template>
  <el-col v-show="!hidden" class="bms-grid-item" :span="span" :offset="offset" :xs="xs" :sm="sm" :md="md" :lg="lg" :xl="xl">
    <slot />
  </el-col>
</template>
