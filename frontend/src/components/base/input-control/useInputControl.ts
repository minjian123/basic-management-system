/**
 * 输入形态片段（`input-control`）：输入型组件通用形态。
 *
 * 契约见《组件设计 · 输入形态片段》：受控绑定、插槽、清空、只读、composition 与 focus / blur。
 * 片段只处理「输入行为」，不含具体控件与校验（校验归字段链与表单容器）。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 输入形态片段参数（`T` 为输入值的原始类型，默认 string） */
export interface UseInputControlOptions<T = string> {
  modelValue?: MaybeRefOrGetter<T>
  placeholder?: MaybeRefOrGetter<string>
  readonly?: MaybeRefOrGetter<boolean>
  clearable?: MaybeRefOrGetter<boolean>
  autofocus?: MaybeRefOrGetter<boolean>
  /** 值变更回调（宿主实现 `v-model` 双向绑定） */
  onUpdate?: (value: T) => void
  /** 清空回调 */
  onClear?: () => void
}

/** 输入形态片段返回值 */
export interface UseInputControlReturn<T = string> {
  /** 当前输入值 */
  readonly value: T | undefined
  readonly isEmpty: boolean
  /** 是否处于输入法组合态（composition 期间不触发变更回调） */
  readonly isComposing: boolean
  readonly isFocused: boolean
  readonly isReadonly: boolean
  readonly canClear: boolean
  readonly placeholder: string
  /** 外部变更入口（接受原生事件或裸值） */
  setValue: (input: T | { target: { value: unknown } }) => void
  clear: () => void
  onCompositionStart: () => void
  onCompositionEnd: (input?: T | { target: { value: unknown } }) => void
  onFocus: () => void
  onBlur: () => void
}

/**
 * 获取输入形态能力。
 *
 * 用法：`const input = useInputControl({ modelValue, onUpdate: (v) => emit('update:modelValue', v) })`。
 */
export function useInputControl<T = string>(options: UseInputControlOptions<T> = {}): UseInputControlReturn<T> {
  declareFragment('input-control')

  const isComposing = ref(false)
  const isFocused = ref(false)

  const value = computed(() => toValue(options.modelValue))
  const isEmpty = computed(() => value.value === undefined || value.value === null || String(value.value) === '')
  const isReadonly = computed(() => Boolean(toValue(options.readonly)))
  const canClear = computed(() => Boolean(toValue(options.clearable)) && !isEmpty.value && !isReadonly.value)
  const placeholder = computed(() => String(toValue(options.placeholder) ?? ''))

  const unwrap = (input: T | { target: { value: unknown } }): T => {
    if (input !== null && typeof input === 'object' && 'target' in input) {
      return (input.target as { value: unknown }).value as T
    }
    return input as T
  }

  const setValue = (input: T | { target: { value: unknown } }): void => {
    if (isReadonly.value) {
      return
    }
    options.onUpdate?.(unwrap(input))
  }

  const clear = (): void => {
    if (!canClear.value) {
      return
    }
    options.onUpdate?.(undefined as unknown as T)
    options.onClear?.()
  }

  const onCompositionStart = (): void => {
    isComposing.value = true
  }

  const onCompositionEnd = (input?: T | { target: { value: unknown } }): void => {
    isComposing.value = false
    if (input !== undefined) {
      setValue(input)
    }
  }

  return {
    get value() {
      return value.value
    },
    get isEmpty() {
      return isEmpty.value
    },
    get isComposing() {
      return isComposing.value
    },
    get isFocused() {
      return isFocused.value
    },
    get isReadonly() {
      return isReadonly.value
    },
    get canClear() {
      return canClear.value
    },
    get placeholder() {
      return placeholder.value
    },
    setValue,
    clear,
    onCompositionStart,
    onCompositionEnd,
    onFocus: () => {
      isFocused.value = true
    },
    onBlur: () => {
      isFocused.value = false
    },
  }
}
