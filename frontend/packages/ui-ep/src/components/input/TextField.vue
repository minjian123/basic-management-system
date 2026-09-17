<script setup lang="ts">
/**
 * 文本框（PC / Element Plus 侧）：单行文本输入（《组件设计 · 文本框》）。
 *
 * 结构：输入域包装 `BaseInput`（字段壳）+ `el-input` 内核；长度 / 正则 / 脱敏 / 三态经域口径；
 * 事件：`update:modelValue`（受控值）、`change`（失焦归一后值）、`validate`（必填 + 长度 + 正则）。
 */

import { ElInput } from 'element-plus'
import 'element-plus/es/components/input/style/css'

import { ref, watch } from 'vue'

import { useComponentBase } from '@bms/vue'

import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    /** 受控值 */
    modelValue?: string | null
    /** 最大长度（内核截断 + 计数） */
    maxlength?: number
    /** 最小长度（校验） */
    minlength?: number
    /** 显示字数统计 */
    showWordLimit?: boolean
    /** 正则（提交前校验，与后端一致） */
    pattern?: string
    /** 失焦归一时去首尾空格 */
    trim?: boolean
    /** 脱敏展示（只读回显） */
    mask?: boolean
    /** 显示明文（配合 `mask`） */
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
    /** 字段标识（权限 / 校验定位预留） */
    fieldKey?: string
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
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  change: [value: string | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'text-field' })

/** 当前受控值（props 与内部写入共同维护，供自身规则校验取用） */
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
      <ElInput
        :model-value="(slot.value as string | null) ?? ''"
        :maxlength="maxlength"
        :minlength="minlength"
        :show-word-limit="showWordLimit"
        :placeholder="placeholder"
        :clearable="clearable"
        :disabled="slot.disabled"
        :readonly="slot.readonly"
        :size="size"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="slot.setValue"
        @focus="slot.onFocus"
        @blur="slot.onBlur"
        @compositionstart="slot.onCompositionStart"
        @compositionend="slot.onCompositionEnd"
        @clear="slot.clear"
      >
        <template v-if="$slots.prefix" #prefix>
          <slot name="prefix" />
        </template>
        <template v-if="$slots.suffix" #suffix>
          <slot name="suffix" />
        </template>
      </ElInput>
    </template>
  </BaseInput>
</template>
