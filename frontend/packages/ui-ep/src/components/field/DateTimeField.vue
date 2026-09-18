<script setup lang="ts">
// 日期时间字段（06_02）：日期 / 日期时间 / 区间；值用 `Date` 对象；组件内校验 + `invalid` + `errorMessage` 回显。
import { ElDatePicker } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 形态（对齐 `el-date-picker` 类型）。 */
export type DateTimeKind = 'date' | 'datetime' | 'daterange' | 'datetimerange'

/** 字段值（区间为二元组）。 */
export type DateTimeValue = Date | [Date, Date] | undefined

interface Props {
  /** 值（受控）。 */
  modelValue?: DateTimeValue
  /** 形态。 */
  kind?: DateTimeKind
  /** 最早可选。 */
  min?: Date
  /** 最晚可选。 */
  max?: Date
  /** 展示格式。 */
  displayFormat?: string
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先于内置校验）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  kind: 'date',
  min: undefined,
  max: undefined,
  displayFormat: '',
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '请选择日期',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: DateTimeValue]
  change: [value: DateTimeValue]
  invalid: [message: string]
  focus: []
  blur: []
}>()

const { value, disabled, setValue, focus, blur, onValueChange } = useBaseInput<DateTimeValue>({
  disabled: props.disabled,
})

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

function list(): Date[] {
  const current = value.value
  if (current === undefined) {
    return []
  }
  return Array.isArray(current) ? current : [current]
}

/** 内置校验（区间顺序 / 范围 / 必填）。 */
const internalError = computed<string>(() => {
  const items = list()
  if (items.length === 0) {
    return props.required ? '该字段为必填项' : ''
  }
  if (Array.isArray(value.value) && value.value.length === 2 && value.value[0].getTime() > value.value[1].getTime()) {
    return '开始时间不能晚于结束时间'
  }
  if (props.min !== undefined && items.some((item) => item.getTime() < props.min!.getTime())) {
    return '不能早于最小时间'
  }
  if (props.max !== undefined && items.some((item) => item.getTime() > props.max!.getTime())) {
    return '不能晚于最大时间'
  }
  return ''
})

/** 对外错误（外部优先）。 */
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
  emit('update:modelValue', next)
  emit('change', next)
})
</script>

<template>
  <div class="bms-date-time-field" :data-invalid="resolvedError !== ''">
    <el-date-picker
      class="bms-date-time-field__picker"
      :type="kind"
      :model-value="value"
      :disabled="disabled"
      :readonly="readonly"
      :placeholder="placeholder"
      :format="displayFormat === '' ? undefined : displayFormat"
      @update:model-value="setValue"
      @focus="focus"
      @blur="blur"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>
