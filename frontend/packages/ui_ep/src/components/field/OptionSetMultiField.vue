<script setup lang="ts">
// 选项集多选件（06_10 返工）：只消费 `optionSetKey`，选项经注入式解析器提供，控件不取数。
// 形态（checkbox / tag / dropdown_multi）由字段属性 widget 决定；写回按选项集顺序去重排序。
// 数量上下限（minItems / maxItems）越限派发 `exceed` 并回退原值；缺项回退原值并开发态告警。
import type { OptionSetItem } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import { isOptionSetDevMode, useOptionSet } from '../../utils/optionSet'
import CheckboxInput from '../input/CheckboxInput.vue'
import SelectInput from '../input/SelectInput.vue'

/** 形态（与控件语义键一致：多选三形态）。 */
export type OptionSetMultiForm = 'checkbox' | 'tag' | 'dropdown_multi'

/** 选项集多选值类型。 */
export type OptionSetMultiValue = string | number

interface Props {
  /** 值（受控，数组）。 */
  modelValue?: OptionSetMultiValue[]
  /** 选项集标识（表单元数据下发；唯一来源）。 */
  optionSetKey?: string
  /** 形态（缺省 `checkbox`）。 */
  form?: OptionSetMultiForm
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
  /** i18n 翻译（`labelKey` → 当前 locale 文本；未注入即回退 `label`）。 */
  translate?: (labelKey: string) => string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  optionSetKey: '',
  form: 'checkbox',
  minItems: undefined,
  maxItems: undefined,
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '',
  errorMessage: '',
  translate: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: OptionSetMultiValue[]]
  change: [value: OptionSetMultiValue[]]
  invalid: [message: string]
  /** 超出数量上下限。 */
  exceed: [value: OptionSetMultiValue[]]
}>()

const { value, disabled, setValue } = useBaseInput<OptionSetMultiValue[]>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(Array.isArray(next) ? next : []),
  { immediate: true },
)

/** 选项集解析（注入式解析器；未注入 / 未下发即空态）。 */
const { items, empty, labelsOf } = useOptionSet({
  optionSetKey: () => props.optionSetKey,
  translate: () => props.translate,
})

/**
 * 当前选中值（去重保序，按选项集顺序输出——写回统一口径）。
 *
 * 以 ref 保持引用稳定（值未变不产生新数组），避免下游控件反复回写造成渲染递归。
 */
const selected = ref<OptionSetMultiValue[]>([])
watch(
  [value, items],
  () => {
    // 受控值已在上方 watch 中归一为数组（`undefined` / 非法值均落 `[]`），此处直接取用。
    const current = value.value as OptionSetMultiValue[]
    const order = new Map<string, number>(items.value.map((item, index) => [item.value, index]))
    const next = [...new Set(current.map((item) => String(item)))].sort(
      (left, right) => (order.get(left) ?? Number.MAX_SAFE_INTEGER) - (order.get(right) ?? Number.MAX_SAFE_INTEGER),
    )
    if (next.length === selected.value.length && next.every((item, index) => item === selected.value[index])) {
      return
    }
    selected.value = next
  },
  { immediate: true },
)

/** 缺项（回显值不在选项集内；空态不算缺项）。 */
const missing = computed(
  () => !empty.value && selected.value.some((item) => items.value.every((option) => option.value !== String(item))),
)

/** 缺项告警（仅开发态、每件一次）。 */
const warned = ref(false)
watch(
  missing,
  (isMissing) => {
    if (!isMissing || warned.value) {
      return
    }
    warned.value = true
    if (isOptionSetDevMode()) {
      console.warn(`[bms] 选项集 ${props.optionSetKey} 缺少选项值：${selected.value.join('、')}`)
    }
  },
  { immediate: true },
)

const internalError = computed<string>(() => {
  // 只读态不校验（存量值超限 / 缺项均照常回显）。
  if (props.readonly || empty.value) {
    return ''
  }
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

/** 只读回显（按选项集顺序取 label，**顿号分隔**；缺 label 回退原值）。 */
const readonlyText = computed(() => (selected.value.length === 0 ? '—' : labelsOf(selected.value)))

/** 控件禁用（空态一并禁用）。 */
const controlDisabled = computed(() => disabled.value || empty.value)

/** 占位提示（空态提示无可选枚举）。 */
const controlPlaceholder = computed(() => (empty.value ? '暂无可选枚举' : props.placeholder))

/**
 * 值变更（越限时派发 `exceed` 并回退原值，值与环境恒一致）。
 *
 * @param next 控件回传值。
 */
function onUpdate(next: OptionSetMultiValue[]): void {
  const normalized = [...new Set(next.map((item) => String(item)))]
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

/**
 * 下拉多选变更（宽类型回传 → 值数组）。
 *
 * @param next 下拉件回传值。
 */
function onSelectUpdate(next: unknown): void {
  const values = Array.isArray(next) ? next : next === undefined || next === null ? [] : [next]
  onUpdate(values as OptionSetMultiValue[])
}

/** 复选基础控件形态（checkbox / tag）。 */
const checkboxForm = computed<'checkbox' | 'tag'>(() => (props.form === 'tag' ? 'tag' : 'checkbox'))

/** 复选基础控件选项（解析结果与基础控件选项同形）。 */
const controlOptions = computed<OptionSetItem[]>(() => items.value)
</script>

<template>
  <div
    class="bms-option-set-multi-field"
    :data-invalid="resolvedError !== ''"
    :data-empty="empty"
    :data-missing="missing || undefined"
    :data-form="form"
  >
    <div
      v-if="readonly"
      class="bms-option-set-multi-field__readonly"
      data-test="option-set-multi-readonly"
    >
      {{ readonlyText }}
    </div>

    <select-input
      v-else-if="form === 'dropdown_multi'"
      class="bms-option-set-multi-field__control"
      :model-value="selected"
      :options="controlOptions"
      multiple
      searchable
      clearable
      collapse-tags
      :disabled="controlDisabled"
      :placeholder="controlPlaceholder"
      @update:model-value="onSelectUpdate"
    />

    <checkbox-input
      v-else
      class="bms-option-set-multi-field__control"
      :model-value="selected"
      :options="controlOptions"
      :form="checkboxForm"
      :disabled="controlDisabled"
      @update:model-value="onUpdate"
    />

    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-option-set-multi-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-option-set-multi-field__control {
  width: 100%;
}

.bms-option-set-multi-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
