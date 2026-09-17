<script setup lang="ts">
/**
 * 数字框（PC / Element Plus 侧）：纯数值输入（《组件设计 · 数字框》）。
 *
 * 内核 `el-input-number`（精度 / 步进 / 上下限原生支持）；对外只发 `number | null`；
 * `thousands` 仅显示层；越界按 `clamp` 钳制或经 `validate(false)` 报告。
 */

import { applyPrecision, clampNumber, formatNumber, inNumberRange, parseFormattedNumber } from '@bms/core'

import { ElInputNumber } from 'element-plus'
import 'element-plus/es/components/input-number/style/css'

import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useComponentBase } from '@bms/vue'

import BaseInput from './BaseInput.vue'

defineOptions({ inheritAttrs: false })

interface ShellExpose {
  setValue(value: unknown): void
  clear(): void
  commit(): unknown
}

const props = withDefaults(
  defineProps<{
    /** 受控值（对外只发数值 / `null`） */
    modelValue?: number | null
    /** 小数位（0 = 整数） */
    precision?: number
    min?: number
    max?: number
    /** 步进 */
    step?: number
    /** 千分位显示（仅显示层，存储为数值） */
    thousands?: boolean
    /** 越界钳制（false 时保留输入并以 `validate(false)` 报告） */
    clamp?: boolean
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
    precision: 0,
    min: undefined,
    max: undefined,
    step: 1,
    thousands: false,
    clamp: true,
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
  'update:modelValue': [value: number | null]
  change: [value: number | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'number-input' })
const { t } = useI18n()

const shellRef = ref<ShellExpose | null>(null)
const current = ref<number | null>(props.modelValue)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

/** 视图取值归一（模板内不做类型断言，避免 `|` 被判为旧式过滤器语法） */
function coerceNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

function handleShellValue(value: unknown): void {
  current.value = typeof value === 'number' ? value : null
  emit('update:modelValue', current.value)
}

/** 控件写入：经壳写域（禁用 / 只读被域拒绝） */
function handleInnerUpdate(value: unknown): void {
  shellRef.value?.setValue(typeof value === 'number' ? value : null)
}

/** 失焦前归一：精度 + 越界钳制（写域后再交壳 `onBlur` 做归一与 `change` 上报） */
function normalizeBeforeBlur(): void {
  const raw = current.value
  if (typeof raw !== 'number') {
    return
  }
  const precise = applyPrecision(raw, props.precision)
  const next = props.clamp ? clampNumber(precise, props.min, props.max) : precise
  if (next !== raw) {
    shellRef.value?.setValue(next)
  }
}

function ownValid(value: number | null): boolean {
  if (value === null || props.clamp) {
    return true
  }
  return inNumberRange(value, props.min, props.max)
}

function handleShellChange(value: unknown): void {
  emit('change', typeof value === 'number' ? value : null)
}

/** 壳的校验结果（必填）与件规则（越界）合并后上报（件结果最后发出，避免被覆盖） */
function handleShellValidate(shellValid: boolean): void {
  emit('validate', shellValid && ownValid(current.value))
}

const outOfRange = computed(
  () => current.value !== null && !props.clamp && !inNumberRange(current.value, props.min, props.max),
)

const helpText = computed(() => (outOfRange.value ? t('input.outOfRange') : props.help))

/** 只读态文本（千分位 / 精度与显示口径一致） */
const readonlyText = computed(() =>
  current.value === null
    ? ''
    : formatNumber(current.value, { precision: props.precision, thousands: props.thousands }),
)

function formatThousands(value: number | string): string {
  const numeric = typeof value === 'number' ? value : Number(parseFormattedNumber(String(value)))
  return Number.isFinite(numeric)
    ? formatNumber(numeric, { precision: props.precision, thousands: true })
    : String(value)
}

function parseThousands(text: string): string {
  return parseFormattedNumber(text)
}
</script>

<template>
  <BaseInput
    ref="shellRef"
    v-bind="$attrs"
    :class="base.nsClass('number-input')"
    :model-value="modelValue"
    :label="label"
    :required="required"
    :help="helpText"
    :error="error"
    :disabled="disabled"
    :readonly="readonly"
    :readonly-mode="readonlyMode"
    :size="size"
    :density="density"
    :span="span"
    :trim="false"
    :field-key="fieldKey"
    :display-text="readonlyText"
    @update:model-value="handleShellValue"
    @change="handleShellChange"
    @validate="handleShellValidate"
  >
    <template #default="slot">
      <ElInputNumber
        :model-value="coerceNumber(slot.value)"
        :precision="precision"
        :min="clamp ? min : undefined"
        :max="clamp ? max : undefined"
        :step="step"
        :formatter="thousands ? formatThousands : undefined"
        :parser="thousands ? parseThousands : undefined"
        :disabled="slot.disabled"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="handleInnerUpdate"
        @focus="slot.onFocus"
        @blur="
          () => {
            normalizeBeforeBlur()
            slot.onBlur()
          }
        "
      />
    </template>
  </BaseInput>
</template>
