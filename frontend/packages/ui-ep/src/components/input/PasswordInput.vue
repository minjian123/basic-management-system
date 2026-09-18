<script setup lang="ts">
// 密码框：密码输入（明文切换 / 强度提示 / 不回填），受控经 `useBaseInput`。
import { ElInput } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseInput } from '../../composables/useBaseInput'

/** 强度档。 */
export type PasswordStrength = 'weak' | 'medium' | 'strong'

interface Props {
  /** 值（受控）。 */
  modelValue?: string
  /** 禁用。 */
  disabled?: boolean
  /** 只读。 */
  readonly?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 明文切换。 */
  showToggle?: boolean
  /** 强度提示（关闭则不显示强度条）。 */
  strength?: boolean
  /** 最大长度。 */
  maxlength?: number
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  disabled: false,
  readonly: false,
  placeholder: '',
  showToggle: true,
  strength: true,
  maxlength: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  'strength-change': [strength: PasswordStrength]
}>()

const { value, disabled, setValue, onValueChange } = useBaseInput<string>({
  disabled: props.disabled,
  placeholder: props.placeholder,
})

watch(
  () => props.modelValue,
  (next) => setValue(next),
  { immediate: true },
)

/** 强度（长度 + 字符类别）。 */
const strengthLevel = computed<PasswordStrength>(() => {
  const text = value.value ?? ''
  const categories = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((pattern) => pattern.test(text)).length
  if (text.length < 8 || categories <= 1) {
    return 'weak'
  }
  return text.length >= 12 && categories >= 3 ? 'strong' : 'medium'
})

onValueChange((next) => {
  const normalized = next ?? ''
  emit('update:modelValue', normalized)
  emit('change', normalized)
  emit('strength-change', strengthLevel.value)
})
</script>

<template>
  <div class="bms-password-input">
    <el-input
      class="bms-password-input__field"
      type="password"
      autocomplete="new-password"
      :model-value="value"
      :disabled="disabled"
      :readonly="readonly"
      :placeholder="placeholder"
      :show-password="showToggle"
      :maxlength="maxlength"
      @update:model-value="setValue"
    />
    <div v-if="strength" class="bms-password-input__strength" :data-strength="strengthLevel" data-test="password-strength" />
  </div>
</template>
