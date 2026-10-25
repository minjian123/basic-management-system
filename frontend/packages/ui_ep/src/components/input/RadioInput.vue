<script setup lang="ts">
// 单选：radio / button / segmented 三形态（静态选项），受控经 `useBaseInput`。
import { ElRadio, ElRadioButton, ElRadioGroup, ElSegmented } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'
import type { InputOption, InputOptions } from './types'

/** 选项值类型。 */
export type RadioValue = string | number

/** 形态。 */
export type RadioForm = 'radio' | 'button' | 'segmented'

interface Props {
  /** 值（受控）。 */
  modelValue?: RadioValue
  /** 静态选项。 */
  options?: InputOptions
  /** 形态。 */
  form?: RadioForm
  /** 禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  options: () => [],
  form: 'radio',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: RadioValue | undefined]
  change: [value: RadioValue | undefined]
}>()

const { value, disabled, setValue, onValueChange } = useBaseInput<RadioValue>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

/** 扁平选项（分组不适用于单选，取分组内合并）。 */
const flatOptions = computed<InputOption[]>(() =>
  props.options.flatMap((option) => ((option as InputOption).value !== undefined ? [option as InputOption] : (option as { options: InputOption[] }).options)),
)

onValueChange((next) => {
  emit('update:modelValue', next)
  emit('change', next)
})

/**
 * 归一 `el-radio-group` / `el-segmented` 的宽类型值。
 *
 * @param next 组件回传值。
 */
function onUpdate(next: string | number | boolean | undefined): void {
  setValue(next as RadioValue | undefined)
}
</script>

<template>
  <el-segmented
    v-if="form === 'segmented'"
    class="bms-radio-input"
    :model-value="value"
    :options="flatOptions"
    :disabled="disabled"
    @update:model-value="onUpdate"
  />
  <el-radio-group
    v-else
    class="bms-radio-input"
    :model-value="value"
    :disabled="disabled"
    @update:model-value="onUpdate"
  >
    <template v-for="(option, index) in flatOptions" :key="index">
      <el-radio-button v-if="form === 'button'" :value="option.value" :disabled="option.disabled">
        {{ option.label }}
      </el-radio-button>
      <el-radio v-else :value="option.value" :disabled="option.disabled">
        {{ option.label }}
      </el-radio>
    </template>
  </el-radio-group>
</template>
