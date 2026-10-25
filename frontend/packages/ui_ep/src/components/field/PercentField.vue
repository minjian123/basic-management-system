<script setup lang="ts">
// 百分比件（11_03 新增，06_03 §2/§6）：输入框右侧固定 `%` 后缀。
// 两种口径：`percent`（输入即百分数，`12.34` → `12.34%`，缺省）/ `ratio`（输入比值，`0.1234` → `12.34%`）；
// 范围按口径缺省（`percent` → 0~100 / `ratio` → 0~1），精度缺省 2、可配 4（费率类）。
import { ElInput } from 'element-plus'
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 口径（对齐节点 §6）。 */
export type PercentScale = 'percent' | 'ratio'

interface Props {
  /** 值（受控；`percent` 口径为百分数，`ratio` 口径为比值）。 */
  modelValue?: number
  /** 口径（缺省 `percent`）。 */
  scale?: PercentScale
  /** 精度（小数位，缺省 2）。 */
  precision?: number
  /** 最小（按口径）。 */
  min?: number
  /** 最大（按口径）。 */
  max?: number
  /** 允许负数（增长率）。 */
  allowNegative?: boolean
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读（纯文本回显带 `%`）。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  scale: 'percent',
  precision: 2,
  min: undefined,
  max: undefined,
  allowNegative: false,
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '请输入百分比',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: number | undefined]
  change: [value: number | undefined]
  invalid: [message: string]
}>()

const { value, disabled, setValue } = useBaseInput<number>({ disabled: props.disabled })
/** 编辑期原文（保持用户输入，失焦后归一）。 */
const editing = ref('')
const focused = ref(false)

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

/** 生效范围（按口径给缺省）。 */
const bounds = computed<{ min: number; max: number }>(() => ({
  min: props.min ?? (props.allowNegative ? -Infinity : 0),
  max: props.max ?? (props.scale === 'ratio' ? 1 : 100),
}))

/** 展示值（编辑期保留原文，否则按精度归一）。 */
const display = computed(() => {
  if (focused.value) {
    return editing.value
  }
  const current = value.value
  if (current === undefined || !Number.isFinite(current)) {
    return ''
  }
  return String(Number(current.toFixed(props.precision)))
})

const internalError = computed<string>(() => {
  const current = value.value
  if (current === undefined) {
    return props.required ? '该字段为必填项' : ''
  }
  if (!Number.isFinite(current)) {
    return '请输入数字'
  }
  if (!props.allowNegative && current < 0) {
    return '不允许负数'
  }
  if (current < bounds.value.min) {
    return `不能小于 ${bounds.value.min}`
  }
  if (current > bounds.value.max) {
    return `不能大于 ${bounds.value.max}`
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

/** 只读回显（按口径换算为百分数文本，带 `%`）。 */
const readonlyText = computed(() => {
  const current = value.value
  if (current === undefined || !Number.isFinite(current)) {
    return '—'
  }
  const asPercent = props.scale === 'ratio' ? current * 100 : current
  return `${Number(asPercent.toFixed(props.precision))}%`
})

/**
 * 输入变更（空串归一到未设置；非法原文不提交）。
 *
 * @param text 输入原文。
 */
function onInput(text: string): void {
  editing.value = text
  const trimmed = text.trim().replace(/%$/, '')
  if (trimmed === '') {
    setValue(undefined)
    emit('update:modelValue', undefined)
    emit('change', undefined)
    return
  }
  const numeric = Number(trimmed)
  if (!Number.isFinite(numeric)) {
    return
  }
  const normalized = Number(numeric.toFixed(props.precision))
  setValue(normalized)
  emit('update:modelValue', normalized)
  emit('change', normalized)
}

function onFocus(): void {
  focused.value = true
  editing.value = value.value === undefined ? '' : String(value.value)
}

function onBlur(): void {
  focused.value = false
}
</script>

<template>
  <div class="bms-percent-field" :data-invalid="resolvedError !== ''" :data-scale="scale">
    <div v-if="readonly" class="bms-percent-field__readonly" data-test="percent-readonly">{{ readonlyText }}</div>

    <el-input
      v-else
      class="bms-percent-field__input"
      data-test="percent-input"
      :model-value="display"
      :disabled="disabled"
      :placeholder="placeholder"
      @update:model-value="onInput"
      @focus="onFocus"
      @blur="onBlur"
    >
      <template #append>%</template>
    </el-input>

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-percent-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-percent-field__input {
  width: 100%;
}

.bms-percent-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
