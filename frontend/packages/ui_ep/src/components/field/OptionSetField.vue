<script setup lang="ts">
// 选项集单选件（06_10 返工）：只消费 `optionSetKey`，选项经注入式解析器（useOptionSet）提供，控件不取数。
// 形态（radio / button / segmented / dropdown）由字段属性 widget 决定；选项数 > 8 的建议由
// `core` 的 `suggestOptionWidget` 产出，件本身不隐式切换形态。
// 缺项回退原值并在开发态告警；空态（无 key / 未下发快照 / 解析为空）禁用降级、零请求。
import type { OptionSetItem } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import { isOptionSetDevMode, useOptionSet } from '../../utils/optionSet'
import RadioInput from '../input/RadioInput.vue'
import SelectInput from '../input/SelectInput.vue'

/** 形态（与控件语义键一致：单选四形态）。 */
export type OptionSetFieldForm = 'radio' | 'button' | 'segmented' | 'dropdown'

/** 选项集值类型。 */
export type OptionSetFieldValue = string | number

interface Props {
  /** 值（受控）。 */
  modelValue?: OptionSetFieldValue
  /** 选项集标识（表单元数据下发；唯一来源）。 */
  optionSetKey?: string
  /** 形态（缺省 `radio`）。 */
  form?: OptionSetFieldForm
  /** 默认值（字段属性 default，新增表单预填）。 */
  defaultValue?: OptionSetFieldValue
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
  /** i18n 翻译（`labelKey` → 当前 locale 文本；未注入即回退 `label`）。 */
  translate?: (labelKey: string) => string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  optionSetKey: '',
  form: 'radio',
  defaultValue: undefined,
  required: false,
  disabled: false,
  readonly: false,
  placeholder: '请选择',
  errorMessage: '',
  translate: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: OptionSetFieldValue | undefined]
  change: [value: OptionSetFieldValue | undefined]
  invalid: [message: string]
}>()

const { value, disabled, setValue } = useBaseInput<OptionSetFieldValue>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next ?? props.defaultValue),
  { immediate: true },
)

/** 选项集解析（注入式解析器；未注入 / 未下发即空态）。 */
const { items, empty, labelOf } = useOptionSet({
  optionSetKey: () => props.optionSetKey,
  translate: () => props.translate,
})

/** 缺项（回显值不在选项集内；空态不算缺项，避免与占位降级重复提示）。 */
const missing = computed(() => !empty.value && value.value !== undefined && labelOf(value.value) === undefined)

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
      console.warn(`[bms] 选项集 ${props.optionSetKey} 缺少选项值：${String(value.value)}`)
    }
  },
  { immediate: true },
)

const internalError = computed<string>(() => {
  // 只读态不校验（存量脏值回退原值展示，编辑态再要求重选）。
  if (props.readonly || empty.value) {
    return ''
  }
  if (value.value === undefined) {
    return props.required ? '该字段为必填项' : ''
  }
  if (labelOf(value.value) === undefined) {
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

/** 只读回显（取 label，缺 label 回退原值；未设置占位 `—`）。 */
const readonlyText = computed(() => {
  if (value.value === undefined) {
    return '—'
  }
  return labelOf(value.value) ?? String(value.value)
})

/** 控件禁用（空态一并禁用，避免空下拉可点）。 */
const controlDisabled = computed(() => disabled.value || empty.value)

/** 占位提示（空态提示无可选枚举）。 */
const controlPlaceholder = computed(() => (empty.value ? '暂无可选枚举' : props.placeholder))

/**
 * 值变更（受控回写 + 变更通知）。
 *
 * @param next 新值。
 */
function onUpdate(next: OptionSetFieldValue | undefined): void {
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
  onUpdate(single as OptionSetFieldValue | undefined)
}

/** 单选基础控件形态（下拉形态由模板分支拦下，此处仅做类型收窄）。 */
const radioForm = computed(() => props.form as 'radio' | 'button' | 'segmented')

/** 单选基础控件选项（解析结果与基础控件选项同形）。 */
const controlOptions = computed<OptionSetItem[]>(() => items.value)
</script>

<template>
  <div
    class="bms-option-set-field"
    :data-invalid="resolvedError !== ''"
    :data-empty="empty"
    :data-missing="missing || undefined"
    :data-form="form"
  >
    <div v-if="readonly" class="bms-option-set-field__readonly" data-test="option-set-readonly">
      {{ readonlyText }}
    </div>

    <select-input
      v-else-if="form === 'dropdown'"
      class="bms-option-set-field__control"
      :model-value="value"
      :options="controlOptions"
      searchable
      clearable
      :disabled="controlDisabled"
      :placeholder="controlPlaceholder"
      @update:model-value="onSelectUpdate"
    />
    <radio-input
      v-else
      class="bms-option-set-field__control"
      :model-value="value"
      :options="controlOptions"
      :form="radioForm"
      :disabled="controlDisabled"
      @update:model-value="onUpdate"
    />
    <p v-if="resolvedError !== ''" class="bms-field-error" data-test="field-error">{{ resolvedError }}</p>
  </div>
</template>

<style scoped>
.bms-option-set-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-option-set-field__control {
  width: 100%;
}

.bms-option-set-field__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
