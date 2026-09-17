<script setup lang="ts">
/**
 * 文本域（移动端 / Vant 侧）：多行文本输入（《组件设计 · 文本域》，与 `ui-ep` 同契约）。
 *
 * 行数 / 自适应高度 / 字数统计交给 `van-field`（`type="textarea"`）；
 * 换行符统一为 `\n`（后端存储口径），提交原样保留。
 */

import { Field as VanField } from 'vant/es/field'
import 'vant/es/field/style'

import { computed, ref, watch } from 'vue'

import { useComponentBase } from '@bms/vue'

import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    /** 受控值 */
    modelValue?: string | null
    /** 初始行数（按行高 24px 折算 Vant 自适应高度） */
    rows?: number
    /** 高度自适应（boolean 或 { minRows, maxRows }） */
    autosize?: boolean | { minRows?: number; maxRows?: number }
    maxlength?: number
    showWordLimit?: boolean
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
    span?: number
    fieldKey?: string
  }>(),
  {
    modelValue: null,
    rows: 3,
    autosize: false,
    maxlength: undefined,
    showWordLimit: false,
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
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  change: [value: string | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'textarea-field' })

const current = ref<string | null>(props.modelValue ?? null)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

/** Vant 自适应高度按像素配置；`{ minRows, maxRows }` 以 24px 行高折算（JS 运行时计算值） */
const ROLE_HEIGHT = 24
const vantAutosize = computed<boolean | { minHeight?: number; maxHeight?: number }>(() => {
  if (props.autosize === false) {
    return false
  }
  if (props.autosize === true) {
    return true
  }
  const { minRows, maxRows } = props.autosize
  return {
    minHeight: minRows !== undefined ? minRows * ROLE_HEIGHT : undefined,
    maxHeight: maxRows !== undefined ? maxRows * ROLE_HEIGHT : undefined,
  }
})

/** 换行符归一：`\r\n` / `\r` → `\n`（后端存储口径） */
function normalizeNewline(value: unknown): unknown {
  return typeof value === 'string' ? value.replace(/\r\n?/g, '\n') : value
}

function ownValidate(): boolean {
  return true
}

function handleUpdate(value: unknown): void {
  const next = normalizeNewline(value)
  current.value = (next as string | null) ?? null
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
    :class="base.nsClass('textarea-field')"
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
        type="textarea"
        :model-value="(slot.value as string | null) ?? ''"
        :rows="rows"
        :autosize="vantAutosize"
        :maxlength="maxlength"
        :show-word-limit="showWordLimit"
        :placeholder="placeholder"
        :disabled="slot.disabled"
        :readonly="slot.readonly"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="(value) => slot.setValue(normalizeNewline(value))"
        @focus="slot.onFocus"
        @blur="slot.onBlur"
        @compositionstart="slot.onCompositionStart"
        @compositionend="slot.onCompositionEnd"
        @clear="slot.clear"
      />
    </template>
  </BaseInput>
</template>
