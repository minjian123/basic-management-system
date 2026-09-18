<script setup lang="ts">
// 数字框：纯数字（精度 / 范围 / 步进 / 千分位），受控经 `useBaseInput`。
import { ElInputNumber } from 'element-plus'
import { watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

interface Props {
  /** 值（受控）。 */
  modelValue?: number
  /** 禁用。 */
  disabled?: boolean
  /** 只读。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 最小。 */
  min?: number
  /** 最大。 */
  max?: number
  /** 步进。 */
  step?: number
  /** 精度。 */
  precision?: number
  /** 千分位显示。 */
  thousandSeparator?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  disabled: false,
  readonly: false,
  placeholder: '',
  min: undefined,
  max: undefined,
  step: 1,
  precision: undefined,
  thousandSeparator: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: number | undefined]
  change: [value: number | undefined]
}>()

const { value, disabled, setValue, onValueChange } = useBaseInput<number>({ disabled: props.disabled })

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

/**
 * 千分位格式化（`el-input-number` 展示口径）。
 *
 * @param value 展示值。
 */
function format(value: number | string): string {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) {
    return ''
  }
  return props.thousandSeparator ? numeric.toLocaleString('zh-CN') : String(numeric)
}

onValueChange((next) => {
  emit('update:modelValue', next)
  emit('change', next)
})
</script>

<template>
  <el-input-number
    class="bms-number-input"
    :model-value="value"
    :disabled="disabled"
    :readonly="readonly"
    :placeholder="placeholder"
    :min="min"
    :max="max"
    :step="step"
    :precision="precision"
    :formatter="format"
    @update:model-value="setValue"
  />
</template>
