<script setup lang="ts">
// 折叠面板组：`el-collapse` 薄封装，支持手风琴与多项展开。
import { ElCollapse, type CollapseModelValue } from 'element-plus'

interface Props {
  /** 当前展开项（手风琴为字符串，多项为数组）。 */
  modelValue?: string | string[]
  /** 手风琴模式（仅一项展开）。 */
  accordion?: boolean
}

withDefaults(defineProps<Props>(), { modelValue: undefined, accordion: false })

const emit = defineEmits<{ 'update:modelValue': [value: string | string[]]; change: [value: string | string[]] }>()

function onChange(value: CollapseModelValue): void {
  const next = (Array.isArray(value) ? value : String(value ?? '')) as string | string[]
  emit('update:modelValue', next)
  emit('change', next)
}
</script>

<template>
  <el-collapse class="bms-collapse-panel-group" :model-value="modelValue" :accordion="accordion" @change="onChange">
    <slot />
  </el-collapse>
</template>
