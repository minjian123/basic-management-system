<script setup lang="ts">
/**
 * 密码框（移动端 / Vant 侧）：密码输入（《组件设计 · 密码框》，与 `ui-ep` 同契约）。
 *
 * 安全底线：**不回填**、明文切换仅组件内存态、值不写日志 / 不落存储、可禁自动填充；
 * 强度提示经核心纯函数 `evaluatePasswordStrength`（双端同规则）。
 */

import { evaluatePasswordStrength } from '@bms/core'

import { Field as VanField } from 'vant/es/field'
import 'vant/es/field/style'

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useComponentBase } from '@bms/vue'

import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    /** 受控值（不回填：初值由使用方决定） */
    modelValue?: string | null
    /** 明文切换按钮 */
    showToggle?: boolean
    /** 显示强度提示 */
    strength?: boolean
    /** 最小长度（校验；默认 8） */
    minLength?: number
    /** 阻止浏览器 / 键盘自动填充 */
    noAutofill?: boolean
    placeholder?: string
    disabled?: boolean
    readonly?: boolean
    readonlyMode?: 'text' | 'disabled'
    label?: string
    required?: boolean
    help?: string
    error?: string
    size?: 'small' | 'default' | 'large'
    density?: 'default' | 'compact'
    span?: number
    fieldKey?: string
  }>(),
  {
    modelValue: null,
    showToggle: true,
    strength: false,
    minLength: 8,
    noAutofill: true,
    placeholder: '',
    disabled: false,
    readonly: false,
    readonlyMode: 'text',
    label: '',
    required: false,
    help: '',
    error: '',
    size: 'default',
    density: 'default',
    span: 24,
    fieldKey: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  change: [value: string | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'password-field' })
const { t } = useI18n()

/** 明文切换（仅组件内存态，不触发日志 / 存储） */
const revealed = ref(false)

const current = ref<string | null>(props.modelValue ?? null)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

const strengthResult = computed(() =>
  evaluatePasswordStrength(current.value, { minLength: props.minLength }),
)

/** 自身规则：最小长度（空值跳过；必填归字段壳）；密码不 trim */
function ownValidate(): boolean {
  const text = current.value ?? ''
  if (text === '') {
    return true
  }
  return text.length >= props.minLength
}

function handleUpdate(value: unknown): void {
  current.value = (value as string | null) ?? null
  emit('update:modelValue', current.value)
}

function handleChange(value: unknown): void {
  current.value = (value as string | null) ?? null
  emit('change', current.value)
}

function handleValidate(shellValid: boolean): void {
  emit('validate', shellValid && ownValidate())
}

function toggleReveal(): void {
  revealed.value = !revealed.value
}
</script>

<template>
  <BaseInput
    v-bind="$attrs"
    :class="base.nsClass('password-field')"
    :model-value="modelValue"
    :label="label"
    :required="required"
    :help="help"
    :error="error"
    :disabled="disabled"
    :readonly="readonly"
    :readonly-mode="readonlyMode"
    :size="size"
    :density="density"
    :span="span"
    :trim="false"
    :field-key="fieldKey"
    :mask="true"
    @update:model-value="handleUpdate"
    @change="handleChange"
    @validate="handleValidate"
  >
    <template #default="slot">
      <VanField
        :model-value="(slot.value as string | null) ?? ''"
        :type="revealed ? 'text' : 'password'"
        :autocomplete="noAutofill ? 'new-password' : undefined"
        :placeholder="placeholder"
        :disabled="slot.disabled"
        :readonly="slot.readonly"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="slot.setValue"
        @focus="slot.onFocus"
        @blur="slot.onBlur"
        @compositionstart="slot.onCompositionStart"
        @compositionend="slot.onCompositionEnd"
      >
        <template v-if="showToggle" #right-icon>
          <button
            type="button"
            :class="base.nsClass('input-password-toggle')"
            :aria-label="revealed ? t('input.password.hide') : t('input.password.show')"
            @click="toggleReveal"
          >
            {{ revealed ? t('input.password.hide') : t('input.password.show') }}
          </button>
        </template>
      </VanField>
      <div
        v-if="strength"
        :class="[base.nsClass('input-strength'), base.nsClass(`input-strength--${strengthResult.level}`)]"
        data-testid="password-strength"
      >
        <span :class="base.nsClass('input-strength-label')">
          {{ t(`input.password.${strengthResult.level}`) }}
        </span>
        <span :class="base.nsClass('input-strength-bar')" aria-hidden="true">
          <span :style="{ width: `${(strengthResult.score / 4) * 100}%` }" />
        </span>
      </div>
    </template>
  </BaseInput>
</template>

<style scoped>
.bms-input-password-toggle {
  padding: 0 var(--bms-space-1);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}
.bms-input-strength {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-top: var(--bms-space-1);
}
.bms-input-strength-label {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}
.bms-input-strength-bar {
  flex: 1;
  height: 4px;
  overflow: hidden;
  background: var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
}
.bms-input-strength-bar > span {
  display: block;
  height: 100%;
  background: var(--bms-color-border);
  transition: width 0.2s ease;
}
.bms-input-strength--weak .bms-input-strength-label {
  color: var(--bms-color-danger);
}
.bms-input-strength--weak .bms-input-strength-bar > span {
  background: var(--bms-color-danger);
}
.bms-input-strength--medium .bms-input-strength-label {
  color: var(--bms-color-warning);
}
.bms-input-strength--medium .bms-input-strength-bar > span {
  background: var(--bms-color-warning);
}
.bms-input-strength--strong .bms-input-strength-label {
  color: var(--bms-color-success);
}
.bms-input-strength--strong .bms-input-strength-bar > span {
  background: var(--bms-color-success);
}
</style>
