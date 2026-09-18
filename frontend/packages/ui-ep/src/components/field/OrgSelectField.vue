<script setup lang="ts">
// 组织选择字段（占位版，06_01）：用户 / 岗位 / 组织 / 部门树；数据通路未就绪时禁用降级。
import { watch } from 'vue'

import { useFieldPlaceholder } from '../../composables/useFieldPlaceholder'
import SelectInput from '../input/SelectInput.vue'
import type { InputOptions } from '../input/types'

/** 字段值类型。 */
export type OrgFieldValue = string | number | (string | number)[]

interface Props {
  /** 值（受控）。 */
  modelValue?: OrgFieldValue
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 组织选项（真实实现接入后由 `06_05` 填充）。 */
  options?: InputOptions
  /** 多选（组织字段缺省多选）。 */
  multiple?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: false,
  options: () => [],
  multiple: true,
  disabled: false,
  placeholder: '请选择组织',
  degradeText: '组织数据未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [value: OrgFieldValue | undefined]
  change: [value: OrgFieldValue | undefined]
}>()

const field = useFieldPlaceholder({ ready: props.ready, disabled: props.disabled })

watch(
  () => props.ready,
  (next) => field.setReady(next),
)
</script>

<template>
  <div
    class="bms-org-select-field"
    :data-ready="field.ready.value"
    :data-degraded="field.degraded.value"
  >
    <slot v-if="field.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <select-input
      v-else
      :model-value="modelValue"
      :options="options"
      :multiple="multiple"
      :searchable="true"
      :disabled="field.disabled.value"
      :placeholder="placeholder"
      @update:model-value="emit('update:modelValue', $event)"
      @change="emit('change', $event)"
    />
  </div>
</template>
