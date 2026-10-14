<script setup lang="ts">
// 数值字段（06_02）：精度 / 范围 / 步进 + 单位 + 组件内校验（invalid + errorMessage 覆盖）。
import { computed, watch } from 'vue'

import { decimalPlaces } from '@bms/core'

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
  /** 单位（个 / 件 / 次，仅展示层附加，不参与存储）。 */
  unit?: string
  /** 步进对齐校验（数量类：值须为步进整数倍）。 */
  stepAligned?: boolean
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
  unit: '',
  stepAligned: false,
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
  // 精度以**文本位数**判定：`Number.isInteger(current * 10 ** precision)` 会因浮点乘法误判
  // （如 `0.29 * 100 === 28.999999999999996` → 误报超精度），见 core `decimalPlaces`。
  if (props.precision !== undefined && decimalPlaces(current).fraction > props.precision) {
    return `最多保留 ${props.precision} 位小数`
  }
  if (props.stepAligned && props.step !== undefined && props.step > 0) {
    const ratio = current / props.step
    if (Math.abs(ratio - Math.round(ratio)) > Number.EPSILON * Math.abs(ratio)) {
      return `须为 ${props.step} 的整数倍`
    }
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

/** 只读回显文本（带单位；空值占位 `—`）。 */
const readonlyText = computed(() => {
  const current = value.value
  if (current === undefined || !Number.isFinite(current)) {
    return '—'
  }
  const body = props.thousandSeparator ? current.toLocaleString('zh-CN') : String(current)
  return props.unit === '' ? body : `${body} ${props.unit}`
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
    <div v-if="readonly" class="bms-number-field__readonly" data-test="number-readonly">{{ readonlyText }}</div>

    <number-input
      v-else
      class="bms-number-field__input"
      :model-value="value"
      :min="min"
      :max="max"
      :step="step"
      :precision="precision"
      :thousand-separator="thousandSeparator"
      :disabled="disabled"
      :placeholder="placeholder"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-number-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-number-field__input {
  width: 100%;
}

.bms-number-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
