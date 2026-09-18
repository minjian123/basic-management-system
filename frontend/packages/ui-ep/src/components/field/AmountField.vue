<script setup lang="ts">
// 金额字段（06_02）：十进制字符串（元）+ `precision`（0~6，支持厘 / 毫）+ 定点校验。
import { ElInput } from 'element-plus'
import { computed, ref, watch } from 'vue'

import {
  compareDecimal,
  formatAmount,
  isDecimal,
  normalizeDecimal,
  sanitizePrecision,
} from '@bms/core'

import { useBaseInput } from '../../composables/useBaseInput'

interface Props {
  /** 值（元，十进制字符串）。 */
  modelValue?: string
  /** 精度（小数位，0 ~ 6；缺省 2）。 */
  precision?: number
  /** 币种（展示）。 */
  currency?: string
  /** 最小（含）。 */
  min?: string
  /** 最大（含）。 */
  max?: string
  /** 千分位展示。 */
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
  precision: 2,
  currency: 'CNY',
  min: undefined,
  max: undefined,
  thousandSeparator: true,
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '请输入金额',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  invalid: [message: string]
}>()

const { value, disabled, setValue } = useBaseInput<string>({ disabled: props.disabled })
const editing = ref('')
const focused = ref(false)

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

const precision = computed(() => sanitizePrecision(props.precision))

/** 展示值（千分位 / 币种）。 */
const display = computed(() => {
  if (focused.value) {
    return editing.value
  }
  const current = value.value
  if (current === undefined || current === '' || !isDecimal(current)) {
    return ''
  }
  if (!props.thousandSeparator) {
    return current
  }
  return formatAmount(Number(current), {
    precision: precision.value,
    currency: props.currency === '' ? undefined : props.currency,
  })
})

const internalError = computed<string>(() => {
  const current = value.value
  if (current === undefined || current === '') {
    return props.required ? '该字段为必填项' : ''
  }
  if (!isDecimal(current)) {
    return '请输入有效金额'
  }
  const fraction = current.includes('.') ? current.split('.')[1].length : 0
  if (fraction > precision.value) {
    return `最多保留 ${precision.value} 位小数`
  }
  const normalized = normalizeDecimal(current, precision.value)
  if (props.min !== undefined && compareDecimal(normalized, props.min) < 0) {
    return `不能小于 ${props.min}`
  }
  if (props.max !== undefined && compareDecimal(normalized, props.max) > 0) {
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

function onInput(text: string): void {
  editing.value = text
  const cleaned = text.replace(/,/g, '')
  if (cleaned === '') {
    setValue(undefined)
    emit('update:modelValue', '')
    emit('change', '')
    return
  }
  if (!isDecimal(cleaned)) {
    return
  }
  const normalized = normalizeDecimal(cleaned, precision.value)
  setValue(normalized)
  emit('update:modelValue', normalized)
  emit('change', normalized)
}

function onFocus(): void {
  focused.value = true
  editing.value = value.value ?? ''
}

function onBlur(): void {
  focused.value = false
}
</script>

<template>
  <div class="bms-amount-field" :data-invalid="resolvedError !== ''">
    <el-input
      class="bms-amount-field__input"
      :model-value="display"
      :disabled="disabled"
      :readonly="readonly"
      :placeholder="placeholder"
      @update:model-value="onInput"
      @focus="onFocus"
      @blur="onBlur"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
