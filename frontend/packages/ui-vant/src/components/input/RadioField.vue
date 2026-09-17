<script setup lang="ts">
/**
 * 单选（移动端 / Vant 侧）：**静态选项**单选（《组件设计 · 单选》，与 `ui-ep` 同契约）。
 *
 * 形态映射：`radio` → `van-radio-group` + `van-radio`；`button` / `segmented` → 自绘按钮组容器
 * + `van-button`（Vant 4 无 `ButtonGroup` 按需入口，选中项 `type="primary"` + 状态类区分）；
 * 归一与只读文本走核心领域纯函数。
 */

import { labelOfOption, normalizeOptionValue, type OptionItem, type OptionValue } from '@bms/core'

import { Button as VanButton } from 'vant/es/button'
import { Radio as VanRadio } from 'vant/es/radio'
import { RadioGroup as VanRadioGroup } from 'vant/es/radio-group'
import 'vant/es/button/style'
import 'vant/es/radio/style'
import 'vant/es/radio-group/style'

import { computed, ref, watch } from 'vue'

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
    /** 受控值（单选值 / `null`） */
    modelValue?: OptionValue | null
    /** 静态选项（字典 / 枚举来源归字段类） */
    options?: readonly OptionItem[]
    widget?: 'radio' | 'button' | 'segmented'
    optionType?: 'default' | 'success' | 'warning' | 'danger'
    inline?: boolean
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
    options: () => [],
    widget: 'radio',
    optionType: 'default',
    inline: false,
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
  'update:modelValue': [value: OptionValue | null]
  change: [value: OptionValue | null]
  validate: [valid: boolean]
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'radio-field' })

const shellRef = ref<ShellExpose | null>(null)
const current = ref<OptionValue | null>(props.modelValue)
watch(
  () => props.modelValue,
  (next) => {
    current.value = next ?? null
  },
)

/** 视图取值归一（模板内不做类型断言，避免 `|` 被判为旧式过滤器语法） */
function coerceOptionValue(value: unknown): OptionValue | null {
  if (value === null || value === undefined || Array.isArray(value)) {
    return null
  }
  return value as OptionValue
}

/** 归一后的值（无效值剔除）：只读文本与选中态共用 */
const normalizedValue = computed(
  () => normalizeOptionValue(current.value, props.options, false) as OptionValue | null,
)

const readonlyText = computed(() => labelOfOption(normalizedValue.value, props.options))

function isSelected(value: OptionValue): boolean {
  return normalizedValue.value === value
}

function handleShellValue(value: unknown): void {
  current.value = coerceOptionValue(value)
  emit('update:modelValue', current.value)
}

function handleShellChange(value: unknown): void {
  emit('change', coerceOptionValue(value))
}

function handleShellValidate(shellValid: boolean): void {
  emit('validate', shellValid)
}

/** 点选单入口（内核与契约共用）：禁用项与无效值拒绝 */
function selectOption(value: OptionValue): void {
  const item = props.options.find((option) => option.value === value)
  if (!item || item.disabled === true) {
    return
  }
  shellRef.value?.setValue(normalizeOptionValue(value, props.options, false))
}

function handleInnerUpdate(value: unknown): void {
  const next = coerceOptionValue(value)
  if (next === null) {
    return
  }
  selectOption(next)
}

const rootClass = computed(() => [
  base.nsClass('radio-field'),
  `${base.nsClass('radio-field')}--${props.widget}`,
  props.inline ? 'is-inline-options' : '',
])

/** 按钮 / 分段形态的语义色（选中项） */
const activeType = computed(() => (props.optionType === 'danger' ? 'danger' : 'primary'))

defineExpose({ selectOption })
</script>

<template>
  <BaseInput
    ref="shellRef"
    v-bind="$attrs"
    :class="rootClass"
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
    :display-text="readonlyText"
    @update:model-value="handleShellValue"
    @change="handleShellChange"
    @validate="handleShellValidate"
  >
    <template #default="slot">
      <VanRadioGroup
        v-if="widget === 'radio'"
        :model-value="coerceOptionValue(slot.value)"
        :disabled="slot.disabled"
        :class="[base.nsClass('radio-field-options'), slot.invalid ? 'is-error' : '']"
        @update:model-value="handleInnerUpdate"
      >
        <VanRadio
          v-for="item in options"
          :key="String(item.value)"
          :name="item.value"
          :disabled="item.disabled === true"
        >
          {{ item.label }}
        </VanRadio>
      </VanRadioGroup>

      <div
        v-else
        :class="[
          base.nsClass('radio-field-options'),
          `${base.nsClass('radio-field-options')}--${widget}`,
          slot.invalid ? 'is-error' : '',
        ]"
      >
        <VanButton
          v-for="item in options"
          :key="String(item.value)"
          :class="isSelected(item.value) ? 'bms-radio-field--option-active' : ''"
          :type="isSelected(item.value) ? activeType : 'default'"
          :plain="!isSelected(item.value)"
          size="small"
          :disabled="slot.disabled || item.disabled === true"
          @click="selectOption(item.value)"
        >
          {{ item.label }}
        </VanButton>
      </div>
    </template>
  </BaseInput>
</template>

<style scoped>
.bms-radio-field-options--button,
.bms-radio-field-options--segmented {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-1);
  width: 100%;
}

.bms-radio-field-options--segmented :deep(.van-button) {
  flex: 1;
}
</style>
