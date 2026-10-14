<script setup lang="ts">
// 复选：checkbox / tag 两形态 + 全选 + 数量上下限（静态选项），受控经 `useBaseInput`。
import { ElCheckbox, ElCheckboxButton, ElCheckboxGroup, type CheckboxValueType } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import type { InputOption, InputOptions } from './types'

/** 选项值类型。 */
export type CheckboxValue = string | number

/** 形态。 */
export type CheckboxForm = 'checkbox' | 'tag'

interface Props {
  /** 值（受控，数组）。 */
  modelValue?: CheckboxValue[]
  /** 静态选项。 */
  options?: InputOptions
  /** 形态。 */
  form?: CheckboxForm
  /** 显示全选。 */
  selectAll?: boolean
  /** 最少选中数。 */
  min?: number
  /** 最多选中数。 */
  max?: number
  /** 禁用。 */
  disabled?: boolean
  /** 只读（顿号分隔纯文本回显已选标签——节点 05_07 §4）。 */
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  options: () => [],
  form: 'checkbox',
  selectAll: false,
  min: undefined,
  max: undefined,
  disabled: false,
  readonly: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: CheckboxValue[]]
  change: [value: CheckboxValue[]]
  invalid: [value: CheckboxValue[]]
}>()

const { value, disabled, setValue, onValueChange } = useBaseInput<CheckboxValue[]>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(Array.isArray(next) ? next : []),
  { immediate: true },
)

/** 扁平选项。 */
const flatOptions = computed<InputOption[]>(() =>
  props.options.flatMap((option) => ((option as InputOption).value !== undefined ? [option as InputOption] : (option as { options: InputOption[] }).options)),
)

const selected = computed<CheckboxValue[]>(() => (Array.isArray(value.value) ? value.value : []))
const selectableValues = computed(() => flatOptions.value.filter((option) => option.disabled !== true).map((option) => option.value))
const allChecked = computed(() => selectableValues.value.length > 0 && selectableValues.value.every((item) => selected.value.includes(item)))
const indeterminate = computed(() => selected.value.length > 0 && !allChecked.value)

/**
 * 只读回显文本（节点 05_07 §4）：按选项集顺序取 label，**顿号分隔**，空值占位 `—`；
 * 不在选项集内的历史值回退原值（与 `EnumMultiField` 同口径，不静默丢值）。
 */
const readonlyText = computed(() => {
  const order = new Map<CheckboxValue, number>(flatOptions.value.map((option, index) => [option.value, index]))
  const items = [...new Set(selected.value)].sort(
    (left, right) => (order.get(left) ?? Number.MAX_SAFE_INTEGER) - (order.get(right) ?? Number.MAX_SAFE_INTEGER),
  )
  if (items.length === 0) {
    return '—'
  }
  return items.map((item) => flatOptions.value.find((option) => option.value === item)?.label ?? String(item)).join('、')
})

onValueChange((next) => {
  emit('update:modelValue', next ?? [])
  emit('change', next ?? [])
})

function commit(next: CheckboxValue[]): void {
  if (props.min !== undefined && next.length < props.min) {
    emit('invalid', next)
    return
  }
  if (props.max !== undefined && next.length > props.max) {
    emit('invalid', next)
    return
  }
  setValue(next)
}

function onGroupUpdate(next: CheckboxValue[]): void {
  commit(Array.isArray(next) ? next : [])
}

function onToggleAll(checked: CheckboxValueType): void {
  commit(checked === true || checked === 'true' ? [...selectableValues.value] : [])
}
</script>

<template>
  <div class="bms-checkbox-input" :data-readonly="readonly">
    <div v-if="readonly" class="bms-checkbox-input__readonly" data-test="checkbox-readonly">{{ readonlyText }}</div>

    <template v-else>
      <el-checkbox
        v-if="selectAll"
        class="bms-checkbox-input__all"
        data-test="checkbox-all"
        :model-value="allChecked"
        :indeterminate="indeterminate"
        :disabled="disabled"
        @update:model-value="onToggleAll"
      >
        全选
      </el-checkbox>
      <el-checkbox-group
        class="bms-checkbox-input__group"
        :model-value="selected"
        :disabled="disabled"
        @update:model-value="onGroupUpdate"
      >
        <template v-for="(option, index) in flatOptions" :key="index">
          <el-checkbox-button v-if="form === 'tag'" :value="option.value" :disabled="option.disabled">
            {{ option.label }}
          </el-checkbox-button>
          <el-checkbox v-else :value="option.value" :disabled="option.disabled">
            {{ option.label }}
          </el-checkbox>
        </template>
      </el-checkbox-group>
    </template>
  </div>
</template>

<style scoped>
.bms-checkbox-input {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-checkbox-input__all {
  align-self: flex-start;
  padding-bottom: var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-checkbox-input__group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-2);
  line-height: var(--bms-line-height);
}

.bms-checkbox-input[data-readonly='true'] .bms-checkbox-input__readonly {
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  color: var(--bms-color-text);
  line-height: var(--bms-control-height);
  background: var(--bms-field-readonly-bg);
  border: 1px solid var(--bms-field-readonly-border);
  border-radius: var(--bms-radius-md);
}
</style>
