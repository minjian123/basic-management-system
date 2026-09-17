<script setup lang="ts">
/**
 * 复选（移动端 / Vant 侧）：**静态选项**多选（《组件设计 · 复选》，与 `ui-ep` 同契约）。
 *
 * 形态映射：`checkbox` → `van-checkbox-group` + `van-checkbox`；`tag` → `van-tag` + 轻量选中交互；
 * 归一（无效值剔除、去重、按选项顺序保序）、全选与数量界限走核心领域纯函数。
 */

import {
  isOptionSelectable,
  labelOfOption,
  normalizeOptionValue,
  reachMaxCount,
  type OptionItem,
  type OptionValue,
} from '@bms/core'

import { Checkbox as VanCheckbox } from 'vant/es/checkbox'
import { CheckboxGroup as VanCheckboxGroup } from 'vant/es/checkbox-group'
import { Tag as VanTag } from 'vant/es/tag'
import 'vant/es/checkbox/style'
import 'vant/es/checkbox-group/style'
import 'vant/es/tag/style'

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
    /** 受控值（多值数组） */
    modelValue?: OptionValue[]
    /** 静态选项（字典 / 枚举来源归字段类） */
    options?: readonly OptionItem[]
    widget?: 'checkbox' | 'tag'
    /** 数量下限（失焦校验） */
    min?: number
    /** 数量上限（达上限拒绝再选） */
    max?: number
    /** 显示全选行（忽略禁用项） */
    selectAll?: boolean
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
    modelValue: () => [],
    options: () => [],
    widget: 'checkbox',
    min: undefined,
    max: undefined,
    selectAll: false,
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
  'update:modelValue': [value: OptionValue[]]
  change: [value: OptionValue[]]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'checkbox-field' })
const { t } = useI18n()

const shellRef = ref<ShellExpose | null>(null)
const current = ref<OptionValue[]>([...(props.modelValue ?? [])])
watch(
  () => props.modelValue,
  (next) => {
    current.value = [...(next ?? [])]
  },
)

/** 归一后的值（无效值剔除 / 去重 / 按选项顺序保序） */
const normalizedList = computed(
  () => normalizeOptionValue(current.value, props.options, true) as OptionValue[],
)

const readonlyText = computed(() => labelOfOption(normalizedList.value, props.options))

const selectableOptions = computed(() => props.options.filter((item) => item.disabled !== true))

const allChecked = computed(
  () =>
    selectableOptions.value.length > 0 &&
    selectableOptions.value.every((item) => normalizedList.value.includes(item.value)),
)

const reachedMax = computed(() => reachMaxCount(normalizedList.value, props.max))

const validated = ref(false)

function isSelected(value: OptionValue): boolean {
  return normalizedList.value.includes(value)
}

function isSelectable(item: OptionItem): boolean {
  return isOptionSelectable(item, normalizedList.value, props.max)
}

function handleShellValue(value: unknown): void {
  current.value = Array.isArray(value) ? (value as OptionValue[]) : []
  emit('update:modelValue', normalizedList.value)
}

function handleShellChange(value: unknown): void {
  emit('change', Array.isArray(value) ? (value as OptionValue[]) : [])
}

function ownValid(value: readonly OptionValue[]): boolean {
  if (props.required && value.length === 0) {
    return false
  }
  if (props.min !== undefined && props.min > 0 && value.length < props.min) {
    return false
  }
  return true
}

function handleShellValidate(shellValid: boolean): void {
  validated.value = true
  emit('validate', shellValid && ownValid(normalizedList.value))
}

/** 主动校验（件规则 + 必填；表单容器与契约共用） */
function validate(): boolean {
  validated.value = true
  const valid = ownValid(normalizedList.value)
  emit('validate', valid)
  return valid
}

const helpText = computed(() => {
  if (reachedMax.value) {
    return t('input.maxCount', { max: props.max })
  }
  if (
    validated.value &&
    props.min !== undefined &&
    props.min > 0 &&
    normalizedList.value.length < props.min
  ) {
    return t('input.minCount', { min: props.min })
  }
  return props.help
})

/** 选中 / 取消（内核与契约共用）：禁用项与达上限的未选项拒绝 */
function selectOption(value: OptionValue): void {
  const item = props.options.find((option) => option.value === value)
  if (!item || !isSelectable(item)) {
    return
  }
  const next = normalizedList.value.includes(value)
    ? normalizedList.value.filter((currentValue) => currentValue !== value)
    : [...normalizedList.value, value]
  shellRef.value?.setValue(normalizeOptionValue(next, props.options, true))
}

/** 全选 / 反选（忽略禁用项；`max` 存在时截断到上限，保证值合法） */
function toggleSelectAll(): void {
  const selectableValues = selectableOptions.value.map((item) => item.value)
  let next: OptionValue[]
  if (allChecked.value) {
    next = normalizedList.value.filter((value) => !selectableValues.includes(value))
  } else {
    const merged = [...normalizedList.value]
    for (const value of selectableValues) {
      if (!merged.includes(value)) {
        merged.push(value)
      }
    }
    const limit = props.max !== undefined && props.max > 0 ? props.max : merged.length
    next = merged.slice(0, limit)
  }
  shellRef.value?.setValue(normalizeOptionValue(next, props.options, true))
}

function handleInnerUpdate(value: unknown): void {
  const list = Array.isArray(value) ? (value as OptionValue[]) : []
  shellRef.value?.setValue(normalizeOptionValue(list, props.options, true))
}

const rootClass = computed(() => [
  base.nsClass('checkbox-field'),
  `${base.nsClass('checkbox-field')}--${props.widget}`,
  props.inline ? 'is-inline-options' : '',
])

defineExpose({ selectOption, toggleSelectAll, validate })
</script>

<template>
  <BaseInput
    ref="shellRef"
    v-bind="$attrs"
    :class="rootClass"
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
    :display-text="readonlyText"
    @update:model-value="handleShellValue"
    @change="handleShellChange"
    @validate="handleShellValidate"
  >
    <template #default="slot">
      <VanCheckboxGroup
        v-if="widget === 'checkbox'"
        :model-value="normalizedList"
        :disabled="slot.disabled"
        :class="[base.nsClass('checkbox-field-options'), slot.invalid ? 'is-error' : '']"
        @update:model-value="handleInnerUpdate"
      >
        <VanCheckbox
          v-if="selectAll"
          :model-value="allChecked"
          :disabled="slot.disabled || selectableOptions.length === 0"
          :class="base.nsClass('checkbox-field-select-all')"
          data-testid="checkbox-select-all"
          @update:model-value="toggleSelectAll"
        >
          {{ t('input.selectAll') }}
        </VanCheckbox>
        <VanCheckbox
          v-for="item in options"
          :key="String(item.value)"
          :name="item.value"
          :disabled="!isSelectable(item)"
        >
          {{ item.label }}
        </VanCheckbox>
      </VanCheckboxGroup>

      <div v-else :class="base.nsClass('checkbox-field-tags')">
        <VanTag
          v-for="item in options"
          :key="String(item.value)"
          :type="isSelected(item.value) ? 'primary' : 'default'"
          :plain="!isSelected(item.value)"
          :class="[isSelectable(item) ? '' : 'is-disabled']"
          :data-value="String(item.value)"
          @click="selectOption(item.value)"
        >
          {{ item.label }}
        </VanTag>
      </div>
    </template>
  </BaseInput>
</template>

<style scoped>
.bms-checkbox-field-options {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
}

.bms-checkbox-field-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
}

.bms-checkbox-field-tags :deep(.is-disabled) {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
