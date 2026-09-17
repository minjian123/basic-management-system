<script setup lang="ts">
/**
 * 数字框（移动端 / Vant 侧）：纯数值输入（《组件设计 · 数字框》，与 `ui-ep` 同契约）。
 *
 * 内核 `van-field type="digit"`（数字键盘）；`stepControls` 打开后提供加减按钮（`step` 生效）；
 * 对外只发 `number | null`（输入中间态仅在件内字符串态）；`thousands` 仅显示层。
 */

import { applyPrecision, clampNumber, formatNumber, inNumberRange, parseNumberInput } from '@bms/core'

import { Button as VanButton } from 'vant/es/button'
import { Field as VanField } from 'vant/es/field'
import 'vant/es/button/style'
import 'vant/es/field/style'

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
    /** 显示加减按钮（移动端键盘无上下键，`step` 经其生效） */
    stepControls?: boolean
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
    stepControls: false,
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
const draft = ref<string>(toText(props.modelValue))

function toText(value: number | null): string {
  if (value === null || value === undefined) {
    return ''
  }
  // 编辑态不带千分位（数字键盘不接受分隔符）；千分位仅在只读态展示
  return formatNumber(value, { precision: props.precision })
}

watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
    draft.value = toText(current.value)
  },
)

function handleShellValue(value: unknown): void {
  current.value = typeof value === 'number' ? value : null
  draft.value = toText(current.value)
  emit('update:modelValue', current.value)
}

/** 输入过程：解析并写域（不钳制，钳制在失焦统一处理） */
function handleInput(text: string): void {
  draft.value = text
  const result = parseNumberInput(text, {
    precision: props.precision,
    min: props.min,
    max: props.max,
    clamp: false,
  })
  if (result.value !== null) {
    shellRef.value?.setValue(result.value)
  }
}

/** 失焦：归一（精度 / 钳制 / 空值）后写域，再交壳做归一与 `change` 上报 */
function normalizeBeforeBlur(): void {
  const result = parseNumberInput(draft.value, {
    precision: props.precision,
    min: props.min,
    max: props.max,
    clamp: props.clamp,
  })
  shellRef.value?.setValue(result.value)
  draft.value = toText(result.value)
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

function stepBy(direction: 1 | -1): void {
  const baseValue = current.value ?? 0
  const next = clampNumber(
    applyPrecision(baseValue + direction * props.step, props.precision),
    props.min,
    props.max,
  )
  shellRef.value?.setValue(next)
  draft.value = toText(next)
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
      <VanField
        type="text"
        inputmode="decimal"
        :model-value="draft"
        :placeholder="placeholder"
        :disabled="slot.disabled"
        :readonly="slot.readonly"
        :class="slot.invalid ? 'is-error' : ''"
        @update:model-value="handleInput"
        @focus="slot.onFocus"
        @blur="
          () => {
            normalizeBeforeBlur()
            slot.onBlur()
          }
        "
      >
        <template v-if="stepControls" #button>
          <span :class="base.nsClass('number-input-steppers')">
            <VanButton
              size="small"
              :disabled="slot.disabled || slot.readonly"
              :class="base.nsClass('number-input-step')"
              @click="stepBy(-1)"
            >
              −
            </VanButton>
            <VanButton
              size="small"
              :disabled="slot.disabled || slot.readonly"
              :class="base.nsClass('number-input-step')"
              @click="stepBy(1)"
            >
              ＋
            </VanButton>
          </span>
        </template>
      </VanField>
    </template>
  </BaseInput>
</template>

<style scoped>
.bms-number-input-steppers {
  display: inline-flex;
  gap: var(--bms-space-1);
}
.bms-number-input-step {
  min-width: 28px;
}
</style>
