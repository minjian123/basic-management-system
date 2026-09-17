<script setup lang="ts">
/**
 * 下拉框（PC / Element Plus 侧）：**静态选项**选择（《组件设计 · 下拉框》）。
 *
 * 内核 `el-select` / `el-option` / `el-option-group`；本件只做静态 `options` 原语，
 * 字典 / 枚举 / 远程来源由字段类经选项源能力 `option-source` 接入。
 * 归一（无效值剔除、多选去重保序）与多选上限判定走核心领域纯函数。
 */

import {
  groupOptions,
  isOptionSelectable,
  labelOfOption,
  normalizeOptionValue,
  reachMaxCount,
  type OptionItem,
  type OptionValue,
} from '@bms/core'

import { ElOption, ElOptionGroup, ElSelect } from 'element-plus'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/option/style/css'

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

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
    /** 受控值（单选值 / 多选数组 / `null`） */
    modelValue?: OptionValue | OptionValue[] | null
    /** 静态选项（字典 / 远程来源归字段类） */
    options?: readonly OptionItem[]
    multiple?: boolean
    /** 本地过滤（按选项文本包含匹配） */
    filterable?: boolean
    clearable?: boolean
    /** 多选标签折叠 */
    collapseTags?: boolean
    /** 多选上限（达上限拒绝再选） */
    maxCount?: number
    placeholder?: string
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
    multiple: false,
    filterable: false,
    clearable: true,
    collapseTags: false,
    maxCount: undefined,
    placeholder: '',
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
  'update:modelValue': [value: OptionValue | OptionValue[] | null]
  change: [value: OptionValue | OptionValue[] | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'select-input' })
const { t } = useI18n()

const shellRef = ref<ShellExpose | null>(null)
const current = ref<OptionValue | OptionValue[] | null>(props.modelValue)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

/** 视图取值归一（模板内不做类型断言，避免 `|` 被判为旧式过滤器语法） */
function coerceOptionValue(value: unknown): OptionValue | OptionValue[] | null {
  if (Array.isArray(value)) {
    return value as OptionValue[]
  }
  if (value === null || value === undefined) {
    return null
  }
  return value as OptionValue
}

function handleShellValue(value: unknown): void {
  current.value = (value ?? null) as OptionValue | OptionValue[] | null
  emit('update:modelValue', current.value)
}

/** 控件写入：归一（无效值剔除 / 去重保序）后经壳写域 */
function handleInnerUpdate(value: unknown): void {
  shellRef.value?.setValue(
    normalizeOptionValue(value as OptionValue | OptionValue[] | null, props.options, props.multiple),
  )
}

/** 归一后的值（无效值剔除）：只读文本与上限判定共用 */
const normalizedValue = computed(() =>
  normalizeOptionValue(current.value, props.options, props.multiple),
)

const selectedValues = computed<OptionValue[]>(() => {
  const value = current.value
  if (Array.isArray(value)) {
    return value
  }
  return value === null || value === undefined ? [] : [value]
})

function isSelectable(item: OptionItem): boolean {
  if (!props.multiple) {
    return item.disabled !== true
  }
  return isOptionSelectable(item, selectedValues.value, props.maxCount)
}

const grouped = computed(() => groupOptions(props.options))
const hasGroups = computed(
  () => grouped.value.length > 1 || (grouped.value[0]?.group ?? '') !== '',
)

const placeholderText = computed(() =>
  props.placeholder === '' ? t('input.selectPlaceholder') : props.placeholder,
)

const helpText = computed(() => {
  if (props.multiple && reachMaxCount(selectedValues.value, props.maxCount)) {
    return t('input.maxCount', { max: props.maxCount })
  }
  return props.help
})

/** 选中 / 取消（内部列表与契约共用）：达上限的未选项不可选 */
function selectOption(value: OptionValue): void {
  const item = props.options.find((option) => option.value === value)
  if (!item || !isSelectable(item)) {
    return
  }
  if (!props.multiple) {
    shellRef.value?.setValue(normalizeOptionValue(value, props.options, false))
    return
  }
  const next = selectedValues.value.includes(value)
    ? selectedValues.value.filter((item2) => item2 !== value)
    : [...selectedValues.value, value]
  shellRef.value?.setValue(normalizeOptionValue(next, props.options, true))
}

function handleShellChange(value: unknown): void {
  emit('change', (value ?? null) as OptionValue | OptionValue[] | null)
}

defineExpose({ selectOption })
</script>

<template>
  <BaseInput
    ref="shellRef"
    v-bind="$attrs"
    :class="base.nsClass('select-input')"
    :model-value="modelValue"
    :label="label"
    :required="required"
    :help="helpText"
    :error="error"
    :disabled="disabled"
    :readonly="readonly"
    :readonly-mode="readonlyMode"
    :size="size"
    :density="density"
    :span="span"
    :trim="false"
    :field-key="fieldKey"
    :display-text="labelOfOption(normalizedValue, options)"
    @update:model-value="handleShellValue"
    @change="handleShellChange"
    @validate="emit('validate', $event)"
  >
    <template #default="slot">
      <ElSelect
        :model-value="coerceOptionValue(slot.value)"
        :multiple="multiple"
        :filterable="filterable"
        :clearable="clearable"
        :collapse-tags="collapseTags"
        :placeholder="placeholderText"
        :disabled="slot.disabled"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="handleInnerUpdate"
        @focus="slot.onFocus"
        @blur="slot.onBlur"
        @clear="slot.clear"
      >
        <template v-if="hasGroups">
          <ElOptionGroup v-for="group in grouped" :key="group.group" :label="group.group">
            <ElOption
              v-for="item in group.items"
              :key="String(item.value)"
              :label="item.label"
              :value="item.value"
              :disabled="!isSelectable(item)"
            />
          </ElOptionGroup>
        </template>
        <template v-else>
          <ElOption
            v-for="item in grouped[0]?.items ?? []"
            :key="String(item.value)"
            :label="item.label"
            :value="item.value"
            :disabled="!isSelectable(item)"
          />
        </template>
      </ElSelect>
    </template>
  </BaseInput>
</template>
