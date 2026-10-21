<script setup lang="ts">
// 枚举多选件（11_03 新增，14 选项集字段 §2/§4/§6）：自定义选项集多选，checkbox / tag / dropdown-multi 三形态。
// 复用基础控件类·复选（`input/CheckboxInput.vue`）与下拉框（`input/SelectInput.vue`），本件只补字段语义：
// 选项集解析（sort 升序 → value 去重保留首个）、必填与数量上下限校验、超限 `exceed` 事件、只读顿号回显。
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import CheckboxInput from '../input/CheckboxInput.vue'
import SelectInput from '../input/SelectInput.vue'
import type { InputOption, InputOptions } from '../input/types'

/** 形态（checkbox 复选框组 / tag 标签点选 / dropdown 下拉多选）。 */
export type EnumMultiForm = 'checkbox' | 'tag' | 'dropdown'

/** 枚举值类型。 */
export type EnumMultiValue = string | number

interface Props {
  /** 值（受控，数组）。 */
  modelValue?: EnumMultiValue[]
  /** 自定义选项集。 */
  options?: InputOptions
  /** 形态（缺省 `checkbox`）。 */
  form?: EnumMultiForm
  /** 最少选中数。 */
  minItems?: number
  /** 最多选中数。 */
  maxItems?: number
  /** 必填。 */
  required?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读（顿号分隔纯文本回显）。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  options: () => [],
  form: 'checkbox',
  minItems: undefined,
  maxItems: undefined,
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '',
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: EnumMultiValue[]]
  change: [value: EnumMultiValue[]]
  invalid: [message: string]
  /** 超出数量上下限。 */
  exceed: [value: EnumMultiValue[]]
}>()

const { value, disabled, setValue } = useBaseInput<EnumMultiValue[]>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(Array.isArray(next) ? next : []),
  { immediate: true },
)

/** 扁平选项（分组不参与枚举多选，取分组内合并）。 */
const flatOptions = computed<InputOption[]>(() =>
  props.options.flatMap((option) =>
    (option as InputOption).value !== undefined ? [option as InputOption] : (option as { options: InputOption[] }).options,
  ),
)

/**
 * 选项集解析（节点 §5）：按 `sort` 升序 → 相同 `value` 去重（保留首个）→ 产出只读选项集。
 */
const resolvedOptions = computed<InputOption[]>(() => {
  const sorted = [...flatOptions.value].sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
  const seen = new Set<EnumMultiValue>()
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

/** 当前选中值（去重保序，按选项集顺序输出——节点 §3「写回统一」）。 */
const selected = computed<EnumMultiValue[]>(() => {
  const current = Array.isArray(value.value) ? value.value : []
  const order = new Map<EnumMultiValue, number>(resolvedOptions.value.map((option, index) => [option.value, index]))
  const unique = [...new Set(current)]
  return unique.sort((a, b) => (order.get(a) ?? Number.MAX_SAFE_INTEGER) - (order.get(b) ?? Number.MAX_SAFE_INTEGER))
})

const internalError = computed<string>(() => {
  const count = selected.value.length
  if (count === 0) {
    return props.required ? '该字段为必填项' : ''
  }
  if (props.minItems !== undefined && count < props.minItems) {
    return `至少选择 ${props.minItems} 项`
  }
  if (props.maxItems !== undefined && count > props.maxItems) {
    return `最多选择 ${props.maxItems} 项`
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

/** 只读回显（按选项集顺序取 label，**顿号分隔**；缺 label 回退原值——节点 §8）。 */
const readonlyText = computed(() => {
  if (selected.value.length === 0) {
    return '—'
  }
  return selected.value
    .map((item) => resolvedOptions.value.find((option) => option.value === item)?.label ?? String(item))
    .join('、')
})

/**
 * 值变更（越限时派发 `exceed` 并回退原值，节点 §6）。
 *
 * @param next 复选件回传值。
 */
/**
 * 下拉多选变更（宽类型回传 → 值数组）。
 *
 * @param next 下拉件回传值。
 */
function onSelectUpdate(next: unknown): void {
  const values = Array.isArray(next) ? next : next === undefined || next === null ? [] : [next]
  onUpdate(values as EnumMultiValue[])
}

/**
 * 值变更（越限时派发 `exceed` 并回退原值，节点 §6）。
 *
 * @param next 复选件回传值。
 */
function onUpdate(next: EnumMultiValue[]): void {
  const normalized = [...new Set(Array.isArray(next) ? next : [])]
  if (props.maxItems !== undefined && normalized.length > props.maxItems) {
    emit('exceed', normalized)
    return
  }
  if (props.minItems !== undefined && normalized.length < props.minItems) {
    emit('exceed', normalized)
    return
  }
  setValue(normalized)
  emit('update:modelValue', normalized)
  emit('change', normalized)
}
</script>

<template>
  <div class="bms-enum-multi-field" :data-invalid="resolvedError !== ''" :data-form="form">
    <div v-if="readonly" class="bms-enum-multi-field__readonly" data-test="enum-multi-readonly">
      {{ readonlyText }}
    </div>

    <select-input
      v-else-if="form === 'dropdown'"
      class="bms-enum-multi-field__control"
      :model-value="selected"
      :options="resolvedOptions"
      multiple
      searchable
      clearable
      collapse-tags
      :disabled="disabled"
      :placeholder="placeholder"
      @update:model-value="onSelectUpdate"
    />

    <checkbox-input
      v-else
      class="bms-enum-multi-field__control"
      :model-value="selected"
      :options="resolvedOptions"
      :form="form === 'tag' ? 'tag' : 'checkbox'"
      :disabled="disabled"
      @update:model-value="onUpdate"
    />

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-enum-multi-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-enum-multi-field__control {
  width: 100%;
}

.bms-enum-multi-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
