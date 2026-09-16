<script setup lang="ts">
/**
 * 输入域组件包装（`BaseInput`）：输入域基类的组件轨（**框架无关**）。
 *
 * 契约见《组件设计 · 输入域基类》：统一受控绑定（`modelValue` / `update:modelValue` /
 * `change`）、`disabled` 合并（props / loading / 字段上下文 / 字段权限）、`readonly`、
 * `size` / `placeholder` / `clearable`、前后缀与前后置插槽、原生事件透传。
 * 无 `default` 插槽时渲染原生 `<input>` 兜底；具体控件（`el-input` / Vant）由子类插槽接入。
 * 字段上下文经 `useFieldContext` 注入消费，挂载注册 / 卸载注销。
 */

import { computed, onMounted, onUnmounted, ref, useAttrs } from 'vue'

import { normalizeClassList, type ComponentDensity, type ComponentSize } from '@/base/BaseComponent'
import { useComponentBase } from '@/base/useComponentBase'

import { useInputBase } from './useInputBase'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    ns?: string
    identifier?: string
    size?: ComponentSize
    density?: ComponentDensity
    loading?: boolean
    disabled?: boolean
    visible?: boolean
    dataTest?: string
    modelValue?: unknown
    readonly?: boolean
    placeholder?: string
    clearable?: boolean
    emptyValue?: unknown
    fieldKey?: string
    threeState?: boolean
  }>(),
  {
    ns: 'bms',
    identifier: '',
    size: 'default',
    density: undefined,
    loading: false,
    disabled: false,
    visible: true,
    dataTest: '',
    modelValue: undefined,
    readonly: false,
    placeholder: '',
    clearable: false,
    emptyValue: undefined,
    fieldKey: '',
    threeState: false,
  },
)

const emit = defineEmits<{
  /** 受控值变化 */
  'update:modelValue': [value: unknown]
  /** 值变化（归一后） */
  change: [value: unknown]
  focus: [event: FocusEvent]
  blur: [event: FocusEvent]
  /** 校验结果（值变化自动触发） */
  validate: [passed: boolean]
}>()

const attrs = useAttrs()
const base = useComponentBase(props)
const inputEl = ref<HTMLInputElement | null>(null)

const inputBase = useInputBase<unknown>({
  modelValue: () => props.modelValue,
  disabled: () => props.disabled,
  loading: () => base.loading,
  readonly: () => props.readonly,
  placeholder: () => props.placeholder,
  clearable: () => props.clearable,
  fieldKey: props.fieldKey,
  threeState: () => props.threeState,
  ...(props.emptyValue !== undefined ? { emptyValue: props.emptyValue } : {}),
  onChange: (value) => {
    emit('update:modelValue', value)
    emit('change', value)
    emit('validate', inputBase.validate())
  },
})

/** 根元素属性：组件根令牌协议 + 命名空间 class + 外部 class / style 合并 */
const rootAttrs = computed(() => {
  const classes = [...normalizeClassList(base.nsClass('input')), ...normalizeClassList(attrs.class)]
  const external: Record<string, unknown> = {}
  if (attrs.style !== undefined) {
    external.style = attrs.style
  }
  const merged = base.rootAttrs(external)
  if (classes.length > 0) {
    merged.class = classes
  }
  return merged
})

/** 原生控件透传属性（过滤组件根保留键；class / style 留在根元素） */
const controlAttrs = computed(() => {
  const external = { ...attrs } as Record<string, unknown>
  delete external.class
  delete external.style
  return base.passthroughAttrs(external)
})

const nativeValue = computed(() => {
  const value = inputBase.value
  return value === undefined || value === null ? '' : String(value)
})

const onNativeInput = (event: Event): void => {
  inputBase.setValue((event.target as HTMLInputElement).value)
}

const onNativeFocus = (event: FocusEvent): void => {
  inputBase.onFocus()
  emit('focus', event)
}

const onNativeBlur = (event: FocusEvent): void => {
  inputBase.onBlur()
  emit('blur', event)
}

const onNativeCompositionEnd = (event: CompositionEvent): void => {
  inputBase.onCompositionEnd((event.target as HTMLInputElement).value)
}

const clear = (): void => {
  inputBase.clear()
}

onMounted(() => {
  base.notifyLifecycle('mounted')
  inputBase.registerControl(() => inputEl.value?.focus())
})

onUnmounted(() => {
  inputBase.unregisterControl()
  base.notifyLifecycle('unmounted')
  base.dispose()
})

defineExpose({ base, mechanisms: base.mechanisms, inputBase, clear })
</script>

<template>
  <div v-if="base.visible" v-bind="rootAttrs">
    <span v-if="$slots.prepend" class="bms-input__prepend">
      <slot name="prepend" />
    </span>
    <span v-if="$slots.prefix" class="bms-input__prefix">
      <slot name="prefix" />
    </span>
    <slot
      v-if="$slots.default"
      :base="inputBase"
      :value="inputBase.value"
      :disabled="inputBase.disabled"
      :readonly="inputBase.readonly"
    />
    <input
      v-else
      ref="inputEl"
      v-bind="controlAttrs"
      class="bms-input__native"
      :value="nativeValue"
      :placeholder="inputBase.placeholder"
      :disabled="inputBase.disabled"
      :readonly="inputBase.readonly"
      @input="onNativeInput"
      @focus="onNativeFocus"
      @blur="onNativeBlur"
      @compositionstart="inputBase.onCompositionStart"
      @compositionend="onNativeCompositionEnd"
    />
    <span v-if="inputBase.canClear" class="bms-input__clear" role="button" @click="clear">×</span>
    <slot v-if="inputBase.isUnset" name="empty" />
    <span v-if="$slots.suffix" class="bms-input__suffix">
      <slot name="suffix" />
    </span>
    <span v-if="$slots.append" class="bms-input__append">
      <slot name="append" />
    </span>
  </div>
</template>
