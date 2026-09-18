<script setup lang="ts">
// 栅格布局（24 栅）：`el-row` 薄封装，统一令牌属性协议。
import { ElRow } from 'element-plus'

import { useBaseLayout } from '../../composables/useBaseLayout'

/** 水平对齐。 */
export type GridJustify = 'start' | 'center' | 'end' | 'space-between' | 'space-around'
/** 垂直对齐。 */
export type GridAlign = 'top' | 'middle' | 'bottom'

interface Props {
  /** 列间距（px）。 */
  gutter?: number
  /** 水平对齐。 */
  justify?: GridJustify
  /** 垂直对齐。 */
  align?: GridAlign
}

const props = withDefaults(defineProps<Props>(), { gutter: 0, justify: undefined, align: undefined })

const { hidden } = useBaseLayout({ columns: 24, gap: props.gutter })
</script>

<template>
  <el-row v-show="!hidden" class="bms-grid-layout" :gutter="gutter" :justify="justify" :align="align">
    <slot />
  </el-row>
</template>
