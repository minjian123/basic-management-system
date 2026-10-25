/** 输入件投影：把核心输入组件基类 `BaseInput` 投影为组合式（受控 / 三态 / 禁用合并 / 清空 / 焦点）。 */

import { BaseInput } from '@bms/core'
import { computed, onScopeDispose, ref, type Ref } from 'vue'

/** 具体输入件（可实例化）。 */
class InputState<T> extends BaseInput<T> {}

/** 选项。 */
export interface UseBaseInputOptions {
  /** 初始值。 */
  value?: unknown
  /** 件级禁用。 */
  disabled?: boolean
  /** 加载态。 */
  loading?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 是否可清空。 */
  clearable?: boolean
}

/** `useBaseInput` 返回面。 */
export interface UseBaseInputResult<T = unknown> {
  /** 输入基类实例。 */
  input: BaseInput<T>
  /** 当前值（响应式）。 */
  value: Ref<T | undefined>
  /** 是否空态（响应式，三态之一）。 */
  isEmpty: Ref<boolean>
  /** 禁用（响应式，合并件级与基类）。 */
  disabled: Ref<boolean>
  /** 加载态（响应式）。 */
  loading: Ref<boolean>
  /** 是否聚焦（响应式）。 */
  focused: Ref<boolean>
  /** 尺寸语义值（响应式）。 */
  sizeToken: Ref<string>
  /** 密度（响应式）。 */
  density: Ref<string>
  /** 设置值（同值不触发）。 */
  setValue: (value: T | undefined) => void
  /** 清空（仅可清空时生效）。 */
  clear: () => void
  /** 聚焦。 */
  focus: () => void
  /** 失焦。 */
  blur: () => void
  /** 设置件级禁用。 */
  setDisabled: (value: boolean) => void
  /** 设置加载态。 */
  setLoading: (value: boolean) => void
  /** 订阅值变更。 */
  onValueChange: (listener: (value: T | undefined) => void) => () => void
}

/**
 * 使用输入件投影。
 *
 * @param options 选项。
 * @returns 输入基类实例与响应式面。
 */
export function useBaseInput<T = unknown>(options: UseBaseInputOptions = {}): UseBaseInputResult<T> {
  const input = new InputState<T>()
  const localDisabled = ref(options.disabled ?? false)
  if (options.disabled !== undefined) {
    input.disabled = options.disabled
  }
  if (options.loading !== undefined) {
    input.loading = options.loading
  }
  if (options.placeholder !== undefined) {
    input.placeholder = options.placeholder
  }
  if (options.clearable !== undefined) {
    input.clearable = options.clearable
  }
  if (options.value !== undefined) {
    input.setValue(options.value as T)
  }

  const value = ref<T | undefined>(input.value) as Ref<T | undefined>
  const isEmpty = ref(input.isEmpty)
  const loading = ref(input.loading)
  const focused = ref(input.focused)
  const sizeToken = ref<string>(input.size)
  const density = ref<string>(input.density)
  const disabled = computed(() => localDisabled.value || input.disabled)

  input.onChange((next) => {
    value.value = next
    isEmpty.value = input.isEmpty
  })
  const off = input.onLifecycle((event) => {
    if (event === 'update') {
      value.value = input.value
      isEmpty.value = input.isEmpty
      loading.value = input.loading
      focused.value = input.focused
      sizeToken.value = input.size
      density.value = input.density
    }
  })
  onScopeDispose(off)

  return {
    input,
    value,
    isEmpty,
    disabled,
    loading,
    focused,
    sizeToken,
    density,
    setValue: (next) => input.setValue(next),
    clear: () => input.clear(),
    focus: () => input.focus(),
    blur: () => input.blur(),
    setDisabled: (next) => {
      localDisabled.value = next
    },
    setLoading: (next) => {
      input.loading = next
      input.notifyLifecycle('update')
    },
    onValueChange: (listener) => input.onChange(listener),
  }
}
