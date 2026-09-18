<script setup lang="ts">
// 文本域：多行文本（行数 / 自适应 / 字数统计 / 换行保留），受控经 `useBaseInput`。
import { ElInput } from 'element-plus'
import { watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

interface Props {
  /** 值（受控）。 */
  modelValue?: string
  /** 禁用。 */
  disabled?: boolean
  /** 只读。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 行数（缺省 3）。 */
  rows?: number
  /** 自适应高度（数字即最小行数）。 */
  autosize?: boolean | { minRows?: number; maxRows?: number }
  /** 最大长度。 */
  maxlength?: number
  /** 是否显示字数统计。 */
  showWordLimit?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  disabled: false,
  readonly: false,
  placeholder: '',
  rows: 3,
  autosize: false,
  maxlength: undefined,
  showWordLimit: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  focus: []
  blur: []
}>()

const { value, disabled, setValue, focus, blur, onValueChange } = useBaseInput<string>({
  disabled: props.disabled,
  placeholder: props.placeholder,
})

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

onValueChange((next) => {
  const normalized = next ?? ''
  emit('update:modelValue', normalized)
  emit('change', normalized)
})
</script>

<template>
  <el-input
    class="bms-textarea-input"
    type="textarea"
    :model-value="value"
    :disabled="disabled"
    :readonly="readonly"
    :placeholder="placeholder"
    :rows="rows"
    :autosize="autosize"
    :maxlength="maxlength"
    :show-word-limit="showWordLimit"
    @update:model-value="setValue"
    @focus="focus"
    @blur="blur"
  />
</template>
