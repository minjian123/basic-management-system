<script setup lang="ts">
/**
 * 文本框（移动端 / Vant 侧）：单行文本输入（《组件设计 · 文本框》，与 `ui-ep` 同契约）。
 *
 * 结构：输入域包装 `BaseInput`（字段壳）+ `van-field` 内核；长度 / 正则 / 脱敏 / 三态经域口径。
 */

import { Field as VanField } from 'vant/es/field'
import 'vant/es/field/style'

import { ref, watch } from 'vue'

import { useComponentBase } from '@bms/vue'

import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    /** 受控值 */
    modelValue?: string | null
    maxlength?: number
    minlength?: number
    showWordLimit?: boolean
    /** 正则（提交前校验，与后端一致） */
    pattern?: string
    trim?: boolean
    mask?: boolean
    plain?: boolean
    placeholder?: string
    clearable?: boolean
    disabled?: boolean
    readonly?: boolean
    readonlyMode?: 'text' | 'disabled'
    label?: string
    required?: boolean
    help?: string
    error?: string
    size?: 'small' | 'default' | 'large'
    density?: 'default' | 'compact'
    /** 栅格（24 制；小于 24 按比例占宽） */
    span?: number
    fieldKey?: string
    /** 自动填充提示（移动端键盘联想） */
    autocomplete?: string
  }>(),
  {
    modelValue: null,
    maxlength: undefined,
    minlength: undefined,
    showWordLimit: false,
    pattern: '',
    trim: true,
    mask: false,
    plain: false,
    placeholder: '',
    clearable: true,
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
    autocomplete: 'off',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  change: [value: string | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'text-field' })

const current = ref<string | null>(props.modelValue ?? null)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

let patternWarned = false

/** 自身规则：最小长度 + 正则（空值跳过；必填归字段壳） */
function ownValidate(): boolean {
  const text = current.value ?? ''
  if (text === '') {
    return true
  }
  if (props.minlength !== undefined && text.length < props.minlength) {
    return false
  }
  if (props.pattern !== '') {
    try {
      if (!new RegExp(props.pattern).test(text)) {
        return false
      }
    } catch {
      if (!patternWarned) {
        patternWarned = true
        console.warn(`[bms] TextField：pattern「${props.pattern}」非法，已跳过正则校验`)
      }
    }
  }
  return true
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
</script>

<template>
  <BaseInput
    v-bind="$attrs"
    :class="base.nsClass('text-field')"
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
    :trim="trim"
    :field-key="fieldKey"
    :mask="mask"
    :plain="plain"
    @update:model-value="handleUpdate"
    @change="handleChange"
    @validate="handleValidate"
  >
    <template #default="slot">
      <VanField
        :model-value="(slot.value as string | null) ?? ''"
        :maxlength="maxlength"
        :minlength="minlength"
        :show-word-limit="showWordLimit"
        :placeholder="placeholder"
        :clearable="clearable"
        :disabled="slot.disabled"
        :readonly="slot.readonly"
        :autocomplete="autocomplete"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="slot.setValue"
        @focus="slot.onFocus"
        @blur="slot.onBlur"
        @compositionstart="slot.onCompositionStart"
        @compositionend="slot.onCompositionEnd"
        @clear="slot.clear"
      >
        <template v-if="$slots.prefix" #left-icon>
          <slot name="prefix" />
        </template>
        <template v-if="$slots.suffix" #right-icon>
          <slot name="suffix" />
        </template>
      </VanField>
    </template>
  </BaseInput>
</template>
