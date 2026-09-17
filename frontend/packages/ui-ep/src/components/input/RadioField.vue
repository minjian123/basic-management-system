<script setup lang="ts">
/**
 * 单选（PC / Element Plus 侧）：**静态选项**单选（《组件设计 · 单选》）。
 *
 * 三形态：`radio`（`el-radio-group`）/ `button`（`el-radio-button`）/ `segmented`（`el-segmented`）；
 * 归一（无效值 → `null`）与只读文本走核心领域纯函数（`domain/option`）；
 * 枚举字段由字段类经选项源能力 `option-source` 继承本件。
 */

import { labelOfOption, normalizeOptionValue, type OptionItem, type OptionValue } from '@bms/core'

import { ElRadio, ElRadioButton, ElRadioGroup, ElSegmented } from 'element-plus'
import 'element-plus/es/components/radio/style/css'
import 'element-plus/es/components/radio-group/style/css'
import 'element-plus/es/components/radio-button/style/css'
import 'element-plus/es/components/segmented/style/css'

import { computed, ref, watch } from 'vue'

import { useComponentBase } from '@bms/vue'

import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

interface ShellExpose {
  setValue(value: unknown): void
  clear(): void
  commit(): unknown
}

const props = withDefaults(
  defineProps<{
    /** 受控值（单选值 / `null`） */
    modelValue?: OptionValue | null
    /** 静态选项（字典 / 枚举来源归字段类） */
    options?: readonly OptionItem[]
    /** 形态 */
    widget?: 'radio' | 'button' | 'segmented'
    /** `button` 形态语义色 */
    optionType?: 'default' | 'success' | 'warning' | 'danger'
    /** `radio` 形态横向排列 */
    inline?: boolean
    disabled?: boolean
    readonly?: boolean
    readonlyMode?: 'text' | 'disabled'
    label?: string
    required?: boolean
    help?: string
    error?: string
    size?: 'small' | 'default' | 'large'
    density?: 'default' | 'compact'
    span?: number
    fieldKey?: string
  }>(),
  {
    modelValue: null,
    options: () => [],
    widget: 'radio',
    optionType: 'default',
    inline: false,
    disabled: false,
    readonly: false,
    readonlyMode: 'text',
    label: '',
    required: false,
    help: '',
    error: '',
    size: 'default',
    density: 'default',
    span: 24,
    fieldKey: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: OptionValue | null]
  change: [value: OptionValue | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'radio-field' })

const shellRef = ref<ShellExpose | null>(null)
const current = ref<OptionValue | null>(props.modelValue)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

/** 视图取值归一（模板内不做类型断言，避免 `|` 被判为旧式过滤器语法） */
function coerceOptionValue(value: unknown): OptionValue | null {
  if (value === null || value === undefined || Array.isArray(value)) {
    return null
  }
  return value as OptionValue
}

/** 内核取值（内核不接受 `null`，空值传 `undefined` 表示未选） */
function innerValue(value: unknown): OptionValue | undefined {
  const next = coerceOptionValue(value)
  return next === null ? undefined : next
}

/** 归一后的值（无效值剔除）：只读文本与选中判定共用 */
const normalizedValue = computed(
  () => normalizeOptionValue(current.value, props.options, false) as OptionValue | null,
)

const readonlyText = computed(() => labelOfOption(normalizedValue.value, props.options))

function handleShellValue(value: unknown): void {
  current.value = coerceOptionValue(value)
  emit('update:modelValue', current.value)
}

function handleShellChange(value: unknown): void {
  emit('change', coerceOptionValue(value))
}

function handleShellValidate(shellValid: boolean): void {
  emit('validate', shellValid)
}

/** 点选单入口（内核与契约共用）：禁用项与无效值拒绝 */
function selectOption(value: OptionValue): void {
  const item = props.options.find((option) => option.value === value)
  if (!item || item.disabled === true) {
    return
  }
  shellRef.value?.setValue(normalizeOptionValue(value, props.options, false))
}

function handleInnerUpdate(value: unknown): void {
  const next = coerceOptionValue(value)
  if (next === null) {
    return
  }
  selectOption(next)
}

const rootClass = computed(() => [
  base.nsClass('radio-field'),
  `${base.nsClass('radio-field')}--${props.widget}`,
  props.inline ? 'is-inline-options' : '',
])

const optionTypeClass = computed(() => (props.optionType === 'default' ? '' : `is-${props.optionType}`))

/** `el-segmented` 选项视图（保持 `options` 顺序） */
const segmentedOptions = computed(() =>
  props.options.map((item) => ({
    label: item.label,
    value: item.value,
    disabled: item.disabled === true,
  })),
)

defineExpose({ selectOption })
</script>

<template>
  <BaseInput
    ref="shellRef"
    v-bind="$attrs"
    :class="rootClass"
    :model-value="modelValue"
    :label="label"
    :required="required"
    :help="help"
    :error="error"
    :disabled="disabled"
    :readonly="readonly"
    :readonly-mode="readonlyMode"
    :size="size"
    :density="density"
    :span="span"
    :trim="false"
    :field-key="fieldKey"
    :display-text="readonlyText"
    @update:model-value="handleShellValue"
    @change="handleShellChange"
    @validate="handleShellValidate"
  >
    <template #default="slot">
      <ElRadioGroup
        v-if="widget === 'radio'"
        :model-value="innerValue(slot.value)"
        :disabled="slot.disabled"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="handleInnerUpdate"
        @focus="slot.onFocus"
        @blur="slot.onBlur"
      >
        <ElRadio
          v-for="item in options"
          :key="String(item.value)"
          :value="item.value"
          :disabled="item.disabled === true"
        >
          {{ item.label }}
        </ElRadio>
      </ElRadioGroup>

      <ElRadioGroup
        v-else-if="widget === 'button'"
        :model-value="innerValue(slot.value)"
        :disabled="slot.disabled"
        :class="[slot.invalid ? 'is-error' : '', 'bms-radio-field-group--button']"
        @update:model-value="handleInnerUpdate"
        @focus="slot.onFocus"
        @blur="slot.onBlur"
      >
        <ElRadioButton
          v-for="item in options"
          :key="String(item.value)"
          :value="item.value"
          :disabled="item.disabled === true"
          :class="optionTypeClass"
        >
          {{ item.label }}
        </ElRadioButton>
      </ElRadioGroup>

      <ElSegmented
        v-else
        :model-value="innerValue(slot.value)"
        :options="segmentedOptions"
        :disabled="slot.disabled"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="handleInnerUpdate"
      />
    </template>
  </BaseInput>
</template>

<style scoped>
.bms-radio-field--radio :deep(.el-radio) {
  display: flex;
  height: auto;
  margin-right: 0;
}

.bms-radio-field--radio.is-inline-options :deep(.el-radio) {
  display: inline-flex;
  margin-right: var(--bms-space-4);
}

.bms-radio-field--radio :deep(.el-radio__label) {
  font-size: var(--bms-font-size-base);
}

.bms-radio-field--button :deep(.el-radio-button__inner) {
  font-size: var(--bms-font-size-base);
}

.bms-radio-field--button :deep(.is-success .el-radio-button__inner) {
  --el-radio-button-checked-bg-color: var(--bms-color-success);
  --el-radio-button-checked-border-color: var(--bms-color-success);
}

.bms-radio-field--button :deep(.is-warning .el-radio-button__inner) {
  --el-radio-button-checked-bg-color: var(--bms-color-warning);
  --el-radio-button-checked-border-color: var(--bms-color-warning);
}

.bms-radio-field--button :deep(.is-danger .el-radio-button__inner) {
  --el-radio-button-checked-bg-color: var(--bms-color-danger);
  --el-radio-button-checked-border-color: var(--bms-color-danger);
}
</style>
