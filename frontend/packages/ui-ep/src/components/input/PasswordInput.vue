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
  /** 最小长度（缺省 8；值非空且短于该长度时经 `invalid` 派发——节点 05_03 §3）。 */
  minLength?: number
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  disabled: false,
  readonly: false,
  placeholder: '',
  showToggle: true,
  strength: true,
  maxlength: undefined,
  minLength: 8,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  'strength-change': [strength: PasswordStrength]
  invalid: [message: string]
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

/**
 * 最小长度校验（节点 05_03 §3「最小长度约束参与校验」）。
 *
 * **独立于强度计算**（强度档位规则不变）；空值不判错（编辑态留空表示不修改），
 * 仅值非空且短于 `minLength` 时给文案。
 */
const internalError = computed<string>(() => {
  const text = value.value ?? ''
  if (text === '' || text.length >= props.minLength) {
    return ''
  }
  return `密码长度不能少于 ${props.minLength} 位`
})

watch(
  internalError,
  (message) => {
    if (message !== '') {
      emit('invalid', message)
    }
  },
  { immediate: true },
)

onValueChange((next) => {
  const normalized = next ?? ''
  emit('update:modelValue', normalized)
  emit('change', normalized)
  emit('strength-change', strengthLevel.value)
})
</script>

<template>
  <div class="bms-password-input" :data-invalid="internalError !== ''">
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

    <p v-if="internalError !== ''" class="bms-field-error" data-test="field-error">{{ internalError }}</p>
  </div>
</template>

<style scoped>
.bms-password-input {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  width: 100%;
  min-width: 0;
}

.bms-password-input__field {
  width: 100%;
}

/* 强度条：轨道（`--bms-tristate-bg`）+ 三档填充（语义色 / 宽度）；`6px` 为件内置图形尺寸（白名单⑤）。 */
.bms-password-input__strength {
  position: relative;
  height: 6px;
  overflow: hidden;
  background: var(--bms-tristate-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-password-input__strength::after {
  display: block;
  height: 100%;
  background: var(--bms-color-danger);
  border-radius: var(--bms-radius-sm);
  transition: width 0.2s, background 0.2s;
  content: '';
}

.bms-password-input__strength[data-strength='weak']::after {
  width: 33%;
  background: var(--bms-color-danger);
}

.bms-password-input__strength[data-strength='medium']::after {
  width: 66%;
  background: var(--bms-color-warning);
}

.bms-password-input__strength[data-strength='strong']::after {
  width: 100%;
  background: var(--bms-color-success);
}
</style>
