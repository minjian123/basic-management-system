<script setup lang="ts">
// 字典选择字段（占位版，06_01）：契约先行冻结；数据通路未就绪时不请求、禁用并降级。
import { watch } from 'vue'

import { useFieldPlaceholder } from '../../composables/useFieldPlaceholder'
import SelectInput from '../input/SelectInput.vue'
import type { InputOptions } from '../input/types'

/** 字段值类型。 */
export type DictFieldValue = string | number | (string | number)[]

interface Props {
  /** 值（受控）。 */
  modelValue?: DictFieldValue
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 字典选项（真实实现接入后由 `06_06` 填充）。 */
  options?: InputOptions
  /** 多选。 */
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
  multiple: false,
  disabled: false,
  placeholder: '请选择',
  degradeText: '字典数据未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [value: DictFieldValue | undefined]
  change: [value: DictFieldValue | undefined]
}>()

const field = useFieldPlaceholder({ ready: props.ready, disabled: props.disabled })

watch(
  () => props.ready,
  (next) => field.setReady(next),
)

watch(
  () => props.disabled,
  (next) => {
    if (next) {
      field.setValue(field.value.value)
    }
  },
)
</script>

<template>
  <div
    class="bms-dict-select-field"
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
      :disabled="field.disabled.value"
      :placeholder="placeholder"
      @update:model-value="emit('update:modelValue', $event)"
      @change="emit('change', $event)"
    />
  </div>
</template>
