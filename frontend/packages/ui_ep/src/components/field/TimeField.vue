<script setup lang="ts">
// 时间件（11_03 新增，06_02 §2/§6）：仅时分（可选秒）的纯时刻选择。
// 值模型为时间字符串（`HH:mm` / `HH:mm:ss`），**不涉及时区换算**（纯时刻）；
// 支持最小 / 最大限制与固定步长，只读态纯文本回显。
import { ElTimePicker } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 时间格式（对齐节点 §6：时分 / 时分秒）。 */
export type TimeFieldFormat = 'HH:mm' | 'HH:mm:ss'

interface Props {
  /** 值（受控；时间字符串）。 */
  modelValue?: string
  /** 展示与回传格式（缺省 `HH:mm`）。 */
  format?: TimeFieldFormat
  /** 最早可选（时间字符串，同 `format`）。 */
  min?: string
  /** 最晚可选（时间字符串，同 `format`）。 */
  max?: string
  /** 固定步长（分钟）。 */
  step?: number
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读（纯文本回显）。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  format: 'HH:mm',
  min: undefined,
  max: undefined,
  step: undefined,
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '请选择时间',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  invalid: [message: string]
}>()

const { value, disabled, setValue, onValueChange } = useBaseInput<string>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

/** 时间字符串是否合法（按 `format` 校验）。 */
function isValidTime(text: string): boolean {
  const pattern = props.format === 'HH:mm:ss' ? /^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$/ : /^([01]\d|2[0-3]):[0-5]\d$/
  return pattern.test(text)
}

/** 时间字符串比较键（去冒号后按数值比较，同格式下等价于时间先后）。 */
function timeKey(text: string): number {
  return Number(text.replace(/:/g, ''))
}

const internalError = computed<string>(() => {
  const current = value.value
  if (current === undefined || current === '') {
    return props.required ? '该字段为必填项' : ''
  }
  if (!isValidTime(current)) {
    return '请输入有效时间'
  }
  if (props.min !== undefined && timeKey(current) < timeKey(props.min)) {
    return `不能早于 ${props.min}`
  }
  if (props.max !== undefined && timeKey(current) > timeKey(props.max)) {
    return `不能晚于 ${props.max}`
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

onValueChange((next) => {
  const normalized = next ?? ''
  emit('update:modelValue', normalized)
  emit('change', normalized)
})

/** 只读回显文本（空值占位 `—`）。 */
const readonlyText = computed(() => (value.value === undefined || value.value === '' ? '—' : value.value))

/**
 * 固定步长约束（`el-time-picker` 无 `step`，经禁用非步长刻度实现）。
 *
 * @param total 该维度总量（分 / 秒为 60）。
 * @returns 不在步长上的刻度列表。
 */
function disabledByStep(total: number): number[] {
  const step = props.step
  if (step === undefined || step <= 1) {
    return []
  }
  const disabled: number[] = []
  for (let tick = 0; tick < total; tick += 1) {
    if (tick % step !== 0) {
      disabled.push(tick)
    }
  }
  return disabled
}

/** 禁用分钟（按步长）。 */
function disabledMinutes(): number[] {
  return disabledByStep(60)
}

/** 禁用秒（按步长）。 */
function disabledSeconds(): number[] {
  return disabledByStep(60)
}
</script>

<template>
  <div class="bms-time-field" :data-invalid="resolvedError !== ''">
    <div v-if="readonly" class="bms-time-field__readonly" data-test="time-readonly">{{ readonlyText }}</div>

    <el-time-picker
      v-else
      class="bms-time-field__picker"
      :model-value="value"
      :format="format"
      :value-format="format"
      :disabled="disabled"
      :placeholder="placeholder"
      :disabled-minutes="step === undefined ? undefined : disabledMinutes"
      :disabled-seconds="format === 'HH:mm:ss' && step !== undefined ? disabledSeconds : undefined"
      @update:model-value="setValue"
    />

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-time-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-time-field__picker {
  width: 100%;
}

.bms-time-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
