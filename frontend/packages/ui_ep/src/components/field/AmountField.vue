<script setup lang="ts">
// 金额字段（06_02）：十进制字符串（元）+ `precision`（0~6，支持厘 / 毫）+ 定点校验 + 单位 / 大写提示。
import { ElInput } from 'element-plus'
import { computed, ref, watch } from 'vue'

import {
  compareDecimal,
  decimalPlaces,
  formatDecimal,
  isDecimal,
  normalizeDecimal,
  sanitizePrecision,
  toChineseUpper,
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
  /** 单位（元 / 万元，仅展示层附加，不参与存储）。 */
  unit?: string
  /** 允许负数（如调整额）。 */
  allowNegative?: boolean
  /** 中文大写提示（合同 / 发票场景）。 */
  upperCase?: boolean
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
  unit: '',
  allowNegative: true,
  upperCase: false,
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

/** 币种符号（仅展示层；未知币种直接展示代码）。 */
const currencySymbol = computed(() => {
  const symbols: Record<string, string> = { CNY: '¥', USD: '$', EUR: '€', GBP: '£', JPY: '¥' }
  return props.currency === '' ? '' : (symbols[props.currency] ?? props.currency)
})

/** 展示值（千分位 + 单位；**定点字符串分组，不经浮点**——节点 §3「前端不以浮点数做累加运算」）。 */
const display = computed(() => {
  if (focused.value) {
    return editing.value
  }
  const current = value.value
  if (current === undefined || current === '' || !isDecimal(current)) {
    return ''
  }
  const body = props.thousandSeparator ? formatDecimal(current, { precision: precision.value }) : current
  const withCurrency = `${currencySymbol.value}${body}`
  return props.unit === '' ? withCurrency : `${withCurrency} ${props.unit}`
})

/** 中文大写提示（开启且值合法时展示；节点 §5）。 */
const upperText = computed(() => {
  if (!props.upperCase) {
    return ''
  }
  const current = value.value
  if (current === undefined || current === '' || !isDecimal(current)) {
    return ''
  }
  return toChineseUpper(current, { precision: precision.value })
})

/** 只读回显文本（带千分位 / 单位；空值占位 `—`）。 */
const readonlyText = computed(() => (display.value === '' ? '—' : display.value))

const internalError = computed<string>(() => {
  const current = value.value
  if (current === undefined || current === '') {
    return props.required ? '该字段为必填项' : ''
  }
  if (!isDecimal(current)) {
    return '请输入有效金额'
  }
  if (!props.allowNegative && current.trim().startsWith('-')) {
    return '不允许负数'
  }
  // 精度以**文本位数**判定（浮点乘法会误判，见 core `decimalPlaces`）。
  if (decimalPlaces(current).fraction > precision.value) {
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
    <div v-if="readonly" class="bms-amount-field__readonly" data-test="amount-readonly">{{ readonlyText }}</div>

    <el-input
      v-else
      class="bms-amount-field__input"
      :model-value="display"
      :disabled="disabled"
      :placeholder="placeholder"
      @update:model-value="onInput"
      @focus="onFocus"
      @blur="onBlur"
    />

    <p v-if="upperText !== ''" class="bms-amount-field__upper" data-test="amount-upper">{{ upperText }}</p>
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-amount-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-amount-field__input {
  width: 100%;
}

.bms-amount-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}

.bms-amount-field__upper {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}
</style>
