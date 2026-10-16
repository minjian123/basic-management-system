<script setup lang="ts">
// 枚举字段（06_02）：自定义选项集；下拉为默认，可切单选（radio / button / segmented）。
// 选项集解析（节点 §6.2）：按 `sort` 升序 → 相同 `value` 去重（保留首个）→ 产出只读选项集。
// 只读回显：单选取 label（缺 label 回退原值）、未设置占位 `—`。
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import RadioInput from '../input/RadioInput.vue'
import SelectInput from '../input/SelectInput.vue'
import type { InputOption, InputOptions } from '../input/types'

/** 形态。 */
export type EnumFieldForm = 'select' | 'radio' | 'button' | 'segmented'

/** 枚举值类型。 */
export type EnumFieldValue = string | number

interface Props {
  /** 值（受控）。 */
  modelValue?: EnumFieldValue
  /** 自定义选项集。 */
  options?: InputOptions
  /** 形态。 */
  form?: EnumFieldForm
  /** 默认值（字段属性 default，新增表单预填）。 */
  defaultValue?: EnumFieldValue
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
  options: () => [],
  form: 'select',
  defaultValue: undefined,
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
  (next) => setValue(next ?? props.defaultValue),
  { immediate: true },
)

/** 扁平选项（分组不适用于单选，取分组内合并）。 */
const flatOptions = computed<InputOption[]>(() =>
  props.options.flatMap((option) =>
    (option as InputOption).value !== undefined ? [option as InputOption] : (option as { options: InputOption[] }).options,
  ),
)

/**
 * 选项集解析（节点 §6.2）：按 `sort` 升序 → 相同 `value` 去重（保留首个）。
 */
const resolvedOptions = computed<InputOption[]>(() => {
  const sorted = [...flatOptions.value].sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
  const seen = new Set<EnumFieldValue>()
  const result: InputOption[] = []
  for (const option of sorted) {
    if (seen.has(option.value)) {
      continue
    }
    seen.add(option.value)
    result.push(option)
  }
  return result
})

const emptyOptions = computed(() => resolvedOptions.value.length === 0)

const internalError = computed<string>(() => {
  if (value.value === undefined) {
    return props.required ? '该字段为必填项' : ''
  }
  if (!resolvedOptions.value.some((option) => option.value === value.value)) {
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

/** 只读回显（取 label，缺 label 回退原值；未设置占位 `—`——节点 §8）。 */
const readonlyText = computed(() => {
  if (value.value === undefined) {
    return '—'
  }
  return resolvedOptions.value.find((option) => option.value === value.value)?.label ?? String(value.value)
})

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
  <div class="bms-enum-field" :data-invalid="resolvedError !== ''" :data-empty="emptyOptions" :data-form="form">
    <div v-if="readonly" class="bms-enum-field__readonly" data-test="enum-readonly">{{ readonlyText }}</div>

    <select-input
      v-else-if="form === 'select'"
      class="bms-enum-field__control"
      :model-value="value"
      :options="resolvedOptions"
      :disabled="disabled || emptyOptions"
      :placeholder="emptyOptions ? '暂无可选枚举' : placeholder"
      @update:model-value="onSelectUpdate"
    />
    <radio-input
      v-else
      class="bms-enum-field__control"
      :model-value="value"
      :options="resolvedOptions"
      :form="form"
      :disabled="disabled || emptyOptions"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-enum-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-enum-field__control {
  width: 100%;
}

.bms-enum-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
