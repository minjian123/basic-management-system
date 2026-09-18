<script setup lang="ts">
// 折叠面板项：`el-collapse-item` 薄封装。
import { ElCollapseItem } from 'element-plus'

import { useBaseLayout } from '../../composables/useBaseLayout'

interface Props {
  /** 项键。 */
  name: string
  /** 标题。 */
  title?: string
  /** 是否禁用。 */
  disabled?: boolean
}

withDefaults(defineProps<Props>(), { title: '', disabled: false })

const { hidden } = useBaseLayout()
</script>

<template>
  <el-collapse-item v-show="!hidden" class="bms-collapse-panel" :name="name" :title="title" :disabled="disabled">
    <template v-if="$slots.title" #title>
      <slot name="title" />
    </template>
    <slot />
    <template v-if="$slots.extra" #extra>
      <slot name="extra" />
    </template>
  </el-collapse-item>
</template>
