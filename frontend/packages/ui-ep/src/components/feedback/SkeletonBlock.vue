<script setup lang="ts">
// 骨架屏：列表 / 卡片 / 详情三形态的加载占位。
import { ElSkeleton, ElSkeletonItem } from 'element-plus'

import { useFeedback } from '../../composables/useFeedback'

/** 骨架屏形态。 */
export type SkeletonBlockVariant = 'list' | 'card' | 'detail'

interface Props {
  /** 形态。 */
  variant?: SkeletonBlockVariant
  /** 行数（列表 / 详情）。 */
  rows?: number
  /** 是否播放动画。 */
  animated?: boolean
}

withDefaults(defineProps<Props>(), { variant: 'list', rows: 4, animated: true })

const { begin } = useFeedback()
begin()
</script>

<template>
  <el-skeleton class="bms-skeleton-block" :rows="rows" :animated="animated" :data-variant="variant">
    <template v-if="variant === 'card'" #template>
      <el-skeleton-item variant="image" style="width: 100%; height: 120px" />
      <el-skeleton-item variant="text" style="width: 60%; margin-top: 12px" />
      <el-skeleton-item variant="text" style="width: 100%; margin-top: 8px" />
      <el-skeleton-item variant="text" style="width: 80%; margin-top: 8px" />
    </template>
  </el-skeleton>
</template>
