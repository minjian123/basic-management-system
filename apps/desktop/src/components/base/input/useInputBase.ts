/**
 * 输入域组合式（`useInputBase`）：输入域基类的组合轨。
 *
 * 契约见《组件设计 · 输入域基类》：组合 `useField`（值归一 / 三态 / 校验 / 壳 / 权限）+
 * `useInputControl`（输入形态：composition / 清空 / 焦点），统一受控绑定、`disabled` 合并
 * （props / loading / 字段上下文 / 字段权限）与字段上下文注册。
 * 依赖方向：片段 + 字段上下文机制 + Vue；不依赖 UI 库（具体控件由子类接入）。
 */

import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { useField, type UseFieldOptions, type UseFieldReturn } from '../field/useField'
import { useFieldContext, type FieldContextValue } from '../field-shell/useFieldContext'
import { useInputControl } from '../input-control/useInputControl'

/** 输入域组合式参数 */
export interface UseInputBaseOptions<T = unknown> {
  modelValue?: MaybeRefOrGetter<T>
  /** 三态清空值（缺省 `undefined`） */
  emptyValue?: T
  disabled?: MaybeRefOrGetter<boolean>
  readonly?: MaybeRefOrGetter<boolean>
  loading?: MaybeRefOrGetter<boolean>
  placeholder?: MaybeRefOrGetter<string>
  clearable?: MaybeRefOrGetter<boolean>
  fieldKey?: string
  /** 必填（缺省取字段上下文 `required`） */
  required?: MaybeRefOrGetter<boolean>
  /** 字段权限入参（可见 / 可编辑 / 必填 / 脱敏；缺省由字段上下文与元数据下发） */
  perm?: NonNullable<UseFieldOptions<T>['perm']>
  formatter?: (value: T) => string
  threeState?: MaybeRefOrGetter<boolean>
  validator?: () => string | undefined
  /** 值变更上报（归一 + 判等后，无变化不回调） */
  onChange?: (value: T | undefined) => void
  onValidateFail?: (message: string) => void
}

/** 输入域组合式返回值 */
export interface UseInputBaseReturn<T = unknown> {
  readonly value: T | undefined
  readonly display: string
  readonly isUnset: boolean
  readonly isCleared: boolean
  /** 合并后禁用（含字段上下文与字段权限） */
  readonly disabled: boolean
  /** 合并后只读 */
  readonly readonly: boolean
  readonly placeholder: string
  readonly canClear: boolean
  readonly isFocused: boolean
  readonly isComposing: boolean
  /** 字段编排片段返回值（壳 / 权限 / 值语义，供子类取用） */
  readonly field: UseFieldReturn<T>
  readonly context: FieldContextValue | undefined
  setValue: (value: unknown) => void
  clear: () => void
  /** 校验（不可见 / 只读直通通过）并回传字段上下文 */
  validate: () => boolean
  resetValidation: () => void
  onFocus: () => void
  onBlur: () => void
  onCompositionStart: () => void
  onCompositionEnd: (value?: unknown) => void
  registerControl: (focus?: () => void) => void
  unregisterControl: () => void
}

/**
 * 获取输入域能力。
 *
 * 用法：`const input = useInputBase({ modelValue, fieldKey, onChange })`；
 * 组件在挂载 / 卸载时调用 `registerControl` / `unregisterControl`。
 */
export function useInputBase<T = unknown>(options: UseInputBaseOptions<T> = {}): UseInputBaseReturn<T> {
  const context = useFieldContext()
  const fieldKey = options.fieldKey ?? context?.fieldKey ?? ''

  const required = computed(() =>
    options.required !== undefined ? Boolean(toValue(options.required)) : context?.required === true,
  )

  const field = useField<T>({
    fieldKey,
    required,
    ...(options.perm ? { perm: options.perm } : {}),
    ...(options.modelValue !== undefined ? { modelValue: options.modelValue } : {}),
    ...(options.emptyValue !== undefined ? { emptyValue: options.emptyValue } : {}),
    ...(options.formatter ? { formatter: options.formatter } : {}),
    ...(options.threeState !== undefined ? { threeState: options.threeState } : {}),
    ...(options.onChange ? { onChange: options.onChange } : {}),
    ...(options.validator ? { validator: options.validator } : {}),
    ...(options.onValidateFail ? { onValidateFail: options.onValidateFail } : {}),
  })

  const disabled = computed(
    () =>
      Boolean(toValue(options.disabled)) ||
      Boolean(toValue(options.loading)) ||
      context?.readonly === true ||
      context?.disabled === true ||
      field.perm.disabled,
  )

  const readonly = computed(() => Boolean(toValue(options.readonly)) || context?.readonly === true)

  /** 统一写入口：只读 / 禁用态拒绝写入（字段壳与权限状态的合并结果） */
  const applyValue = (value: unknown): void => {
    if (readonly.value || disabled.value) {
      return
    }
    context?.emitValueChange?.(value)
    field.setValue(value)
  }

  const input = useInputControl<T>({
    // 片段入参口径为 `T`，域层允许 `undefined`（未设置 / 已清空），此处按其只读消费面兼容
    modelValue: () => field.value as T,
    readonly,
    ...(options.clearable !== undefined ? { clearable: options.clearable } : {}),
    ...(options.placeholder !== undefined ? { placeholder: options.placeholder } : {}),
    onUpdate: (value) => {
      applyValue(value)
    },
  })

  const validate = (): boolean => {
    const passed = field.validate()
    context?.emitValidate?.(passed, field.shell.errorText || undefined)
    return passed
  }

  return {
    get value() {
      return field.value
    },
    get display() {
      return field.display
    },
    get isUnset() {
      return field.isUnset
    },
    get isCleared() {
      return field.isCleared
    },
    get disabled() {
      return disabled.value
    },
    get readonly() {
      return readonly.value
    },
    get placeholder() {
      return input.placeholder
    },
    get canClear() {
      return input.canClear
    },
    get isFocused() {
      return input.isFocused
    },
    get isComposing() {
      return input.isComposing
    },
    field,
    context,
    setValue: applyValue,
    clear: () => {
      if (readonly.value || disabled.value) {
        return
      }
      field.clear()
    },
    validate,
    resetValidation: () => {
      field.resetValidation()
    },
    onFocus: () => {
      input.onFocus()
    },
    onBlur: () => {
      input.onBlur()
    },
    onCompositionStart: () => {
      input.onCompositionStart()
    },
    onCompositionEnd: (value?: unknown) => {
      input.onCompositionEnd(value as T)
    },
    registerControl: (focus?: () => void) => {
      context?.registerControl?.({ fieldKey, ...(focus ? { focus } : {}) })
    },
    unregisterControl: () => {
      context?.unregisterControl?.(fieldKey)
    },
  }
}
