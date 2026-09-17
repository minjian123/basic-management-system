<script setup lang="ts">
/**
 * 输入域包装件（PC / Element Plus 侧）：字段壳。
 *
 * - 壳职责：label / 必填星号 / 帮助 / 错误 / 只读回显 / 栅格（24 制 `span`）；
 * - 控件本体经默认插槽放入（作用域参数提供受控值、写入口与事件桥接）；
 * - 域语义（归一 / 清空 / 只读判定 / 写门禁）来自 `@bms/vue` `useInput` → 核心 `createInputContext`；
 * - 只读默认 `readonlyMode="text"`（纯文本回显 + 空值占位），可切 `disabled`（禁用态输入元素）。
 */

import { computed, useAttrs, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useComponentBase, useInput } from '@bms/vue'

const props = withDefaults(
  defineProps<{
    /** 受控值（文本 / 数字 / 布尔 / 多值数组 / 空） */
    modelValue?: string | number | boolean | Array<string | number> | null
    /** 字段标签（空则不渲染标签元素） */
    label?: string
    /** 必填（星号 + 校验） */
    required?: boolean
    /** 帮助文案 */
    help?: string
    /** 外部错误文案（内部校验错误优先展示） */
    error?: string
    disabled?: boolean
    readonly?: boolean
    /** 只读呈现：纯文本 / 禁用态输入元素 */
    readonlyMode?: 'text' | 'disabled'
    size?: 'small' | 'default' | 'large'
    density?: 'default' | 'compact'
    /** 栅格（24 制；小于 24 时按比例占宽） */
    span?: number
    /** 归一时去首尾空格 */
    trim?: boolean
    /** 字段标识（权限 / 校验定位预留） */
    fieldKey?: string
    /** 脱敏展示（只读文本态生效） */
    mask?: boolean
    /** 显示明文（配合 `mask`） */
    plain?: boolean
    /** 只读文本覆盖（缺省用域值直出；数字框千分位 / 下拉框已选文本等场景传） */
    displayText?: string
  }>(),
  {
    modelValue: null,
    label: '',
    required: false,
    help: '',
    error: '',
    disabled: false,
    readonly: false,
    readonlyMode: 'text',
    size: 'default',
    density: 'default',
    span: 24,
    trim: true,
    fieldKey: '',
    mask: false,
    plain: false,
    displayText: undefined,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  change: [value: unknown]
  validate: [valid: boolean]
}>()

const base = useComponentBase({
  ns: 'bms',
  identifier: 'input',
  size: props.size,
  density: props.density,
})
const { t } = useI18n()
const attrs = useAttrs()

const input = useInput<unknown>({
  fieldOptions: {
    value: {
      initial: props.modelValue,
      isEmpty: (value) => value === undefined || value === null || value === '',
      readonly: props.readonly,
    },
    shell: { label: props.label, required: props.required },
    disabled: props.disabled,
  },
  trim: props.trim,
  readonlyMode: props.readonlyMode,
})

/** 值内容比较（数组按内容比较：多值件的受控回写每次都是新引用，引用比较会触发回环） */
function isSameValue(left: unknown, right: unknown): boolean {
  if (left === right) {
    return true
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, index) => item === right[index])
  }
  return false
}

/** 外部受控值回写（跳过与域值相同的更新，避免回环） */
watch(
  () => props.modelValue,
  (next) => {
    if (!isSameValue(next, input.value.value)) {
      input.setValue(next)
    }
  },
)

/** 域值变化即外发（禁用 / 只读时域拒绝写入，故不会外发） */
watch(input.value, (next) => {
  emit('update:modelValue', next)
})

const mode = computed(() => input.mode.value)
const mergedDisabled = computed(() => props.disabled || mode.value === 'disabled')
const isReadonly = computed(() => props.readonly || mode.value !== 'edit')
const invalid = computed(() => input.error.value !== '' || props.error !== '')

const errorText = computed(() => {
  if (input.error.value === 'required') {
    return t('input.required')
  }
  if (input.error.value !== '') {
    return input.error.value
  }
  return props.error
})

/** 只读文本（外部覆盖优先；空值占位；`mask` 且非 `plain` 时脱敏） */
const readonlyText = computed(() => {
  const raw = props.displayText !== undefined ? props.displayText : input.instance.displayText()
  if (raw === '') {
    return t('input.emptyText')
  }
  if (!props.mask || props.plain) {
    return raw
  }
  if (raw.length <= 2) {
    return '*'.repeat(raw.length)
  }
  return `${raw.slice(0, 1)}${'*'.repeat(raw.length - 2)}${raw.slice(-1)}`
})

const slotProps = computed(() => ({
  value: input.value.value,
  setValue: (next: unknown) => {
    input.setValue(next)
  },
  clear: () => {
    input.clear()
  },
  disabled: mergedDisabled.value,
  readonly: isReadonly.value,
  size: props.size,
  invalid: invalid.value,
  onFocus: () => {
    input.focus()
  },
  onBlur: () => {
    onBlur()
  },
  onCompositionStart: () => {
    input.compositionStart()
  },
  onCompositionEnd: () => {
    input.compositionEnd()
  },
}))

/** 失焦：归一写回 + change / validate 上报 */
function onBlur(): void {
  const next = input.commit()
  emit('change', next)
  emit('validate', input.instance.field.validate())
}

/** 档位与禁用状态同步到组件根（`data-size` / `data-density` / 状态类） */
watch(
  () => [props.size, props.density, props.disabled] as const,
  ([size, density, disabled]) => {
    base.setProps({ size, density, disabled })
  },
  { immediate: true },
)

const rootClass = computed(() => [
  base.nsClass('input'),
  props.span < 24 ? 'is-inline' : '',
  input.error.value !== '' || props.error !== '' ? 'is-error' : '',
])

const rootAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [rootClass.value, cls],
    style: [sty, props.span < 24 ? `--bms-input-span: ${props.span}` : ''],
    ...rest,
  })
})

defineExpose({
  get mode() {
    return mode.value
  },
  get error() {
    return errorText.value
  },
  /** 写域（件层经 `shellRef` 调用；禁用 / 只读时域拒绝写入） */
  setValue: (value: unknown) => {
    input.setValue(value)
  },
  /** 清空（`clearable` 为真时） */
  clear: () => {
    input.clear()
  },
  /** 归一 + 写回 + 失焦 */
  commit: () => input.commit(),
})
</script>

<template>
  <div v-bind="rootAttrs" :class="rootClass">
    <label v-if="label !== ''" :class="base.nsClass('input-label')">
      {{ label }}
      <span v-if="required" :class="base.nsClass('input-required')" aria-hidden="true">*</span>
    </label>
    <div :class="base.nsClass('input-control')">
      <span v-if="mode === 'text'" :class="base.nsClass('input-text')" data-testid="input-text">
        {{ readonlyText }}
      </span>
      <slot v-else v-bind="slotProps" />
    </div>
    <p v-if="help !== ''" :class="base.nsClass('input-help')">{{ help }}</p>
    <p v-if="errorText !== ''" :class="base.nsClass('input-error')" role="alert">{{ errorText }}</p>
  </div>
</template>

<style scoped>
.bms-input {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  min-width: 0;
}
.bms-input.is-inline {
  width: calc(var(--bms-input-span, 24) / 24 * 100%);
}
.bms-input-label {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  line-height: var(--bms-line-height-base);
}
.bms-input-required {
  margin-left: 2px;
  color: var(--bms-color-danger);
}
.bms-input-control {
  min-width: 0;
}
.bms-input-text {
  display: block;
  min-height: var(--bms-size-control-height);
  padding: var(--bms-space-1) 0;
  font-size: var(--bms-font-size-base);
  color: var(--bms-color-text);
  word-break: break-word;
  white-space: pre-wrap;
}
.bms-input-help {
  margin: 0;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}
.bms-input-error {
  margin: 0;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}
</style>
