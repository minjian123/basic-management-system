<script setup lang="ts">
// 文本框：单行文本输入（前后缀 / 清空 / 字数限制），受控经 `useBaseInput`。
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
  /** 是否可清空。 */
  clearable?: boolean
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
  clearable: false,
  maxlength: undefined,
  showWordLimit: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  focus: []
  blur: []
  clear: []
}>()

const { value, disabled, setValue, clear, focus, blur, onValueChange } = useBaseInput<string>({
  disabled: props.disabled,
  placeholder: props.placeholder,
  clearable: props.clearable,
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

function onClear(): void {
  clear()
  emit('clear')
}
</script>

<template>
  <el-input
    class="bms-text-input"
    :model-value="value"
    :disabled="disabled"
    :readonly="readonly"
    :placeholder="placeholder"
    :clearable="clearable"
    :maxlength="maxlength"
    :show-word-limit="showWordLimit"
    @update:model-value="setValue"
    @focus="focus"
    @blur="blur"
    @clear="onClear"
  >
    <template v-if="$slots.prefix" #prefix>
      <slot name="prefix" />
    </template>
    <template v-if="$slots.suffix" #suffix>
      <slot name="suffix" />
    </template>
  </el-input>
</template>
