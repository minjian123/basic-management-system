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

<style scoped>
/* 薄封装件：只对齐令牌（标题 / 内容字号与分隔线色） */
.bms-collapse-panel :deep(.el-collapse-item__header) {
  font-size: var(--bms-font-size);
  font-weight: 600;
  color: var(--bms-color-text);
  background: transparent;
  border-bottom-color: var(--bms-color-border);
}

.bms-collapse-panel :deep(.el-collapse-item__wrap) {
  background: transparent;
}

.bms-collapse-panel :deep(.el-collapse-item__content) {
  padding-bottom: var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}
</style>
