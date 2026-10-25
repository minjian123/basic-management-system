<script setup lang="ts">
// 日期时间字段（06_02）：日期 / 日期时间 / 区间 / 时间；值用 `Date` 对象；
// 组件内校验 + `invalid` + `errorMessage` 回显；只读态「起 ~ 止」纯文本回显；快捷键按用户时区边界计算。
// 时区换算（UTC ↔ 用户时区）需语言上下文能力接入，本批登记遗留（见详细设计 §9）。
import { ElDatePicker, ElTimePicker } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 形态（对齐 `el-date-picker` 类型 + `time` 时间件）。 */
export type DateTimeKind = 'date' | 'datetime' | 'daterange' | 'datetimerange' | 'time'

/** 字段值（区间为二元组；`time` 形态为 `Date`）。 */
export type DateTimeValue = Date | [Date, Date] | undefined

/** 快捷键项。 */
export interface DateTimeShortcut {
  /** 文案。 */
  text: string
  /** 取值（返回区间）。 */
  value: () => [Date, Date]
}

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
  /** 范围分隔符（缺省 `~`，对齐节点 §5；EP 缺省为 `-`）。 */
  rangeSeparator?: string
  /** 快捷键（今天 / 昨天 / 最近 7 天 / 最近 30 天 / 本月 / 上月，仅日期与区间生效；缺省开启）。 */
  shortcuts?: boolean
  /** 日期时间型选择日期后补齐的默认时分。 */
  defaultTime?: Date
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读（纯文本回显）。 */
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
  rangeSeparator: '~',
  shortcuts: true,
  defaultTime: undefined,
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

/** 值列表（区间展开为两项）。 */
function list(): Date[] {
  const current = value.value
  if (current === undefined) {
    return []
  }
  return Array.isArray(current) ? current : [current]
}

/** 是否为区间形态。 */
const isRange = computed(() => props.kind === 'daterange' || props.kind === 'datetimerange')

/** 是否为时间形态。 */
const isTime = computed(() => props.kind === 'time')

/** 日期选择器形态（`time` 走独立时间件，此处收敛为日期类形态）。 */
const dateKind = computed(() => (props.kind === 'time' ? 'date' : props.kind))

/** 天边界工具（按用户时区当天 00:00:00 / 23:59:59，节点 §3）。 */
function dayRange(fromOffset: number, toOffset: number): [Date, Date] {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() + fromOffset, 0, 0, 0, 0)
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + toOffset, 23, 59, 59, 999)
  return [start, end]
}

/** 月边界工具。 */
function monthRange(offset: number): [Date, Date] {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth() + offset, 1, 0, 0, 0, 0)
  const end = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0, 23, 59, 59, 999)
  return [start, end]
}

/** 内置快捷键（节点 §5：今天 / 昨天 / 最近 7 天 / 最近 30 天 / 本月 / 上月）。 */
const builtinShortcuts = computed<DateTimeShortcut[]>(() =>
  props.shortcuts
    ? [
        { text: '今天', value: () => dayRange(0, 0) },
        { text: '昨天', value: () => dayRange(-1, -1) },
        { text: '最近 7 天', value: () => dayRange(-6, 0) },
        { text: '最近 30 天', value: () => dayRange(-29, 0) },
        { text: '本月', value: () => monthRange(0) },
        { text: '上月', value: () => monthRange(-1) },
      ]
    : [],
)

/** 生效快捷键（仅区间形态消费）。 */
const effectiveShortcuts = computed(() => (isRange.value ? builtinShortcuts.value : []))

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

/** 日期 / 日期时间格式化（`yyyy-MM-dd` / `yyyy-MM-dd HH:mm`，节点 §7）。 */
function formatDate(date: Date, withTime: boolean): string {
  const pad = (value: number): string => String(value).padStart(2, '0')
  const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  return withTime ? `${day} ${pad(date.getHours())}:${pad(date.getMinutes())}` : day
}

/** 时间格式化（`HH:mm`）。 */
function formatTime(date: Date): string {
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 只读回显文本（区间为「起 ~ 止」；空值占位 `—`；节点 §5/§7）。 */
const readonlyText = computed(() => {
  const items = list()
  if (items.length === 0) {
    return '—'
  }
  if (isTime.value) {
    return formatTime(items[0])
  }
  const withTime = props.kind === 'datetime' || props.kind === 'datetimerange'
  if (items.length === 2) {
    return `${formatDate(items[0], withTime)} ${props.rangeSeparator} ${formatDate(items[1], withTime)}`
  }
  return formatDate(items[0], withTime)
})
</script>

<template>
  <div class="bms-date-time-field" :data-invalid="resolvedError !== ''" :data-kind="kind">
    <div v-if="readonly" class="bms-date-time-field__readonly" data-test="datetime-readonly">{{ readonlyText }}</div>

    <el-time-picker
      v-else-if="isTime"
      class="bms-date-time-field__picker"
      :model-value="value"
      format="HH:mm"
      value-format="HH:mm"
      :disabled="disabled"
      :placeholder="placeholder"
      @update:model-value="setValue"
      @focus="focus"
      @blur="blur"
    />

    <el-date-picker
      v-else
      class="bms-date-time-field__picker"
      :type="dateKind"
      :model-value="value"
      :disabled="disabled"
      :placeholder="placeholder"
      :format="displayFormat === '' ? undefined : displayFormat"
      :range-separator="rangeSeparator"
      :shortcuts="effectiveShortcuts"
      :default-time="defaultTime"
      @update:model-value="setValue"
      @focus="focus"
      @blur="blur"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-date-time-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-date-time-field__picker {
  width: 100%;
}

.bms-date-time-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
