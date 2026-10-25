<script setup lang="ts">
// 单布尔复选：布尔（三态未设置 / 禁用），受控经 `useBaseInput`；语义为单一布尔勾选（非选项多选）。
import { ElCheckbox } from 'element-plus'
import { watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

interface Props {
  /** 值（受控；`undefined` 表示未设置）。 */
  modelValue?: boolean
  /** 复选文案（缺省空）。 */
  label?: string
  /** 禁用。 */
  disabled?: boolean
  /** 不确定态（仅视觉，不改值）。 */
  indeterminate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  label: '',
  disabled: false,
  indeterminate: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
}>()

const { value, disabled, setValue, onValueChange } = useBaseInput<boolean>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

onValueChange((next) => {
  const normalized = next === true
  emit('update:modelValue', normalized)
  emit('change', normalized)
})

/**
 * 勾选变更（归一为布尔并受控更新）。
 *
 * @param next 组件库回传的勾选值。
 */
function onUpdate(next: string | number | boolean): void {
  setValue(next === true)
}
</script>

<template>
  <el-checkbox
    class="bms-boolean-checkbox"
    :model-value="value === true"
    :disabled="disabled"
    :indeterminate="indeterminate"
    @update:model-value="onUpdate"
  >
    {{ label }}
  </el-checkbox>
</template>
