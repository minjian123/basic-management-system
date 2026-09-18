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
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  options: () => [],
  form: 'checkbox',
  selectAll: false,
  min: undefined,
  max: undefined,
  disabled: false,
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
  <div class="bms-checkbox-input">
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
    <el-checkbox-group :model-value="selected" :disabled="disabled" @update:model-value="onGroupUpdate">
      <template v-for="(option, index) in flatOptions" :key="index">
        <el-checkbox-button v-if="form === 'tag'" :value="option.value" :disabled="option.disabled">
          {{ option.label }}
        </el-checkbox-button>
        <el-checkbox v-else :value="option.value" :disabled="option.disabled">
          {{ option.label }}
        </el-checkbox>
      </template>
    </el-checkbox-group>
  </div>
</template>
