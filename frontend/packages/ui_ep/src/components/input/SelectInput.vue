<script setup lang="ts">
// 下拉框：静态选项（单选 / 多选 / 本地搜索 / 分组），受控经 `useBaseInput`；空态复用 `03_02`。
import { ElOption, ElOptionGroup, ElSelect } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import EmptyState from '../feedback/EmptyState.vue'
import type { InputOption, InputOptionGroup, InputOptions } from './types'

/** 选项值类型。 */
export type SelectValue = string | number

interface Props {
  /** 值（受控；多选为数组）。 */
  modelValue?: SelectValue | SelectValue[]
  /** 静态选项（含分组）。 */
  options?: InputOptions
  /** 多选。 */
  multiple?: boolean
  /** 本地搜索。 */
  searchable?: boolean
  /** 可清空。 */
  clearable?: boolean
  /** 多选折叠标签。 */
  collapseTags?: boolean
  /** 禁用。 */
  disabled?: boolean
  /** 只读。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  options: () => [],
  multiple: false,
  searchable: false,
  clearable: false,
  collapseTags: false,
  disabled: false,
  readonly: false,
  placeholder: '请选择',
})

const emit = defineEmits<{
  'update:modelValue': [value: SelectValue | SelectValue[] | undefined]
  change: [value: SelectValue | SelectValue[] | undefined]
  clear: []
}>()

const { value, disabled, setValue, clear, onValueChange } = useBaseInput<SelectValue | SelectValue[]>({
  disabled: props.disabled,
  placeholder: props.placeholder,
  clearable: props.clearable,
})

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

const normalized = computed<SelectValue | SelectValue[] | undefined>(() =>
  props.multiple ? (Array.isArray(value.value) ? value.value : []) : value.value,
)

function isGroup(option: InputOption | InputOptionGroup): option is InputOptionGroup {
  return (option as InputOptionGroup).options !== undefined
}

onValueChange((next) => {
  emit('update:modelValue', next)
  emit('change', next)
})

function onClear(): void {
  clear()
  emit('clear')
}
</script>

<template>
  <el-select
    class="bms-select-input"
    :model-value="normalized"
    :multiple="multiple"
    :filterable="searchable"
    :clearable="clearable"
    :collapse-tags="collapseTags"
    :disabled="disabled"
    :placeholder="placeholder"
    :data-size="undefined"
    @update:model-value="setValue"
    @clear="onClear"
  >
    <template v-for="(option, index) in options" :key="index">
      <el-option-group v-if="isGroup(option)" :label="option.label">
        <el-option
          v-for="child in option.options"
          :key="`${index}-${String(child.value)}`"
          :label="child.label"
          :value="child.value"
          :disabled="child.disabled"
        />
      </el-option-group>
      <el-option
        v-else
        :key="`${index}-${String((option as InputOption).value)}`"
        :label="(option as InputOption).label"
        :value="(option as InputOption).value"
        :disabled="(option as InputOption).disabled"
      />
    </template>
    <template #empty>
      <slot name="empty">
        <empty-state type="result" />
      </slot>
    </template>
  </el-select>
</template>
