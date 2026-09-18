<script setup lang="ts">
// 表单渲染器主体（占位，08_01_02）：由 FormRenderer 异步懒加载的独立分包入口，真实实现（08_06）按元数据分发字段控件。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { FormRenderMode } from './FormRenderer.vue'

interface Props {
  /** 三态。 */
  mode?: FormRenderMode
  /** 布局元数据（`layout-effective`）。 */
  meta?: unknown
  /** 记录数据。 */
  modelValue?: Record<string, unknown>
  /** 标签位置。 */
  labelPosition?: 'top' | 'left'
  /** 强制只读。 */
  forceReadOnly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'create',
  meta: undefined,
  modelValue: () => ({}),
  labelPosition: 'top',
  forceReadOnly: false,
})

const { state, setState } = useBaseDataState()
watch(
  () => props.meta,
  (meta) => setState(meta === undefined || meta === null ? 'empty' : 'ready'),
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-form-renderer-body"
    data-test="renderer-body"
    data-subpackage="renderer"
    :data-mode="mode"
    :data-label-position="labelPosition"
    :data-state="state"
    :data-readonly="forceReadOnly || mode === 'view'"
  >
    <p v-if="state === 'empty'" data-test="renderer-empty">暂无布局元数据（占位，真实实现按 `layout-effective` 渲染）</p>
    <p v-else data-test="renderer-note">按元数据渲染字段区域（占位，真实实现接字段控件分发）</p>
  </div>
</template>
