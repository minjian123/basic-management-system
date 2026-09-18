<script setup lang="ts">
// 数值字段（06_02）：精度 / 范围 / 步进 + 组件内校验（invalid + errorMessage 覆盖）。
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import NumberInput from '../input/NumberInput.vue'

interface Props {
  /** 值（受控）。 */
  modelValue?: number
  /** 最小。 */
  min?: number
  /** 最大。 */
  max?: number
  /** 步进。 */
  step?: number
  /** 精度（小数位）。 */
  precision?: number
  /** 千分位显示。 */
  thousandSeparator?: boolean
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
  min: undefined,
  max: undefined,
  step: 1,
  precision: undefined,
  thousandSeparator: false,
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '请输入数值',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: number | undefined]
  change: [value: number | undefined]
  invalid: [message: string]
}>()

const { value, setValue } = useBaseInput<number>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

/** 精度归一（超位四舍五入）。 */
function roundTo(next: number | undefined): number | undefined {
  if (next === undefined || props.precision === undefined) {
    return next
  }
  const factor = 10 ** props.precision
  return Math.round(next * factor) / factor
}

const internalError = computed<string>(() => {
  const current = value.value
  if (current === undefined) {
    return props.required ? '该字段为必填项' : ''
  }
  if (!Number.isFinite(current)) {
    return '请输入数字'
  }
  if (props.precision !== undefined && !Number.isInteger(current * 10 ** props.precision)) {
    return `最多保留 ${props.precision} 位小数`
  }
  if (props.min !== undefined && current < props.min) {
    return `不能小于 ${props.min}`
  }
  if (props.max !== undefined && current > props.max) {
    return `不能大于 ${props.max}`
  }
  return ''
})

const resolvedError = computed(() => (props.errorMessage !== '' ? props.errorMessage : internalError.value))

watch(internalError, (message) => {
  if (message !== '') {
    emit('invalid', message)
  }
})

function onUpdate(next: number | undefined): void {
  const rounded = roundTo(next)
  setValue(rounded)
  emit('update:modelValue', rounded)
  emit('change', rounded)
}
</script>

<template>
  <div class="bms-number-field" :data-invalid="resolvedError !== ''">
    <number-input
      class="bms-number-field__input"
      :model-value="value"
      :min="min"
      :max="max"
      :step="step"
      :precision="precision"
      :thousand-separator="thousandSeparator"
      :disabled="disabled"
      :readonly="readonly"
      :placeholder="placeholder"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
