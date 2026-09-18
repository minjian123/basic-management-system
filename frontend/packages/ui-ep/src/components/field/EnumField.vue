<script setup lang="ts">
// 枚举字段（06_02）：自定义选项集；下拉为默认，可切单选（radio / button）。
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import RadioInput from '../input/RadioInput.vue'
import SelectInput from '../input/SelectInput.vue'
import type { InputOption, InputOptions } from '../input/types'

/** 形态。 */
export type EnumFieldForm = 'select' | 'radio' | 'button'

/** 枚举值类型。 */
export type EnumFieldValue = string | number

interface Props {
  /** 值（受控）。 */
  modelValue?: EnumFieldValue
  /** 自定义选项集。 */
  options?: InputOptions
  /** 形态。 */
  form?: EnumFieldForm
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  options: () => [],
  form: 'select',
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '请选择',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: EnumFieldValue | undefined]
  change: [value: EnumFieldValue | undefined]
  invalid: [message: string]
}>()

const { value, disabled, setValue } = useBaseInput<EnumFieldValue>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

const flatOptions = computed<InputOption[]>(() =>
  props.options.flatMap((option) =>
    (option as InputOption).value !== undefined ? [option as InputOption] : (option as { options: InputOption[] }).options,
  ),
)
const emptyOptions = computed(() => flatOptions.value.length === 0)

const internalError = computed<string>(() => {
  if (value.value === undefined) {
    return props.required ? '该字段为必填项' : ''
  }
  if (!flatOptions.value.some((option) => option.value === value.value)) {
    return '选项不在选项集中'
  }
  return ''
})

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : internalError.value))

watch(
  internalError,
  (message) => {
    if (message !== '') {
      emit('invalid', message)
    }
  },
  { immediate: true },
)

function onUpdate(next: EnumFieldValue | undefined): void {
  setValue(next)
  emit('update:modelValue', next)
  emit('change', next)
}

/**
 * 归一 `SelectInput` 的宽类型回传（数组取首值）。
 *
 * @param next 组件回传值。
 */
function onSelectUpdate(next: unknown): void {
  const single = Array.isArray(next) ? next[0] : next
  onUpdate(single as EnumFieldValue | undefined)
}
</script>

<template>
  <div class="bms-enum-field" :data-invalid="resolvedError !== ''" :data-empty="emptyOptions">
    <select-input
      v-if="form === 'select'"
      class="bms-enum-field__control"
      :model-value="value"
      :options="options"
      :disabled="disabled || emptyOptions"
      :placeholder="emptyOptions ? '暂无可选枚举' : placeholder"
      @update:model-value="onSelectUpdate"
    />
    <radio-input
      v-else
      class="bms-enum-field__control"
      :model-value="value"
      :options="options"
      :form="form"
      :disabled="disabled || emptyOptions"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
