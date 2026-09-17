/**
 * 输入域投影（Vue 绑定插件）：核心 `createInputContext`（`field` + `input-control`）↔ Vue 响应式。
 *
 * 只做实例化 + 订阅回写 + 作用域释放；域语义（归一 / 清空 / 只读判定 / 写门禁）全在核心。
 */

import { computed, getCurrentScope, onScopeDispose, shallowRef, type ComputedRef, type ShallowRef } from 'vue'

import {
  createCapability,
  createInputContext,
  type BaseField,
  type BaseInputControl,
  type InputContext,
  type InputContextOptions,
  type InputMode,
} from '@bms/core'

export type UseInputOptions<T = unknown> = InputContextOptions<T>

export interface UseInputReturn<T = unknown> {
  /** 核心域上下文（归一 / 提交 / 清空 / 模式判定） */
  instance: InputContext<T>
  /** 受控值（视图绑定） */
  value: ShallowRef<T>
  /** 字段壳错误文案（空串表示无错误） */
  error: ShallowRef<string>
  focused: ShallowRef<boolean>
  composing: ShallowRef<boolean>
  /** 展示态（禁用 > 只读 > 编辑；构造期静态语义） */
  mode: ComputedRef<InputMode>
  disabled: ComputedRef<boolean>
  readonly: ComputedRef<boolean>
  required: ComputedRef<boolean>
  setValue: (value: T) => void
  /** 归一 + 写回 + 失焦（壳层失焦 / 提交前调用），返回提交值 */
  commit: () => T
  clear: () => void
  focus: () => void
  blur: () => void
  compositionStart: () => void
  compositionEnd: () => void
}

export function useInput<T = unknown>(options: UseInputOptions<T> = {}): UseInputReturn<T> {
  const field =
    options.field ?? createCapability<BaseField<T>>('field', { ...(options.fieldOptions ?? {}) })
  const control =
    options.control ??
    createCapability<BaseInputControl>('input-control', { ...(options.controlOptions ?? {}) })
  const instance = createInputContext<T>({ ...options, field, control })

  const value = shallowRef(instance.read())
  const error = shallowRef(field.shell.error.get())
  const focused = shallowRef(control.focused.get())
  const composing = shallowRef(control.composing.get())

  const offValue = field.value.onChange((next) => {
    value.value = next
  })
  const offError = field.shell.error.subscribe((next) => {
    error.value = next
  })
  const offFocus = control.focused.subscribe((next) => {
    focused.value = next
  })
  const offComposing = control.composing.subscribe((next) => {
    composing.value = next
  })

  if (getCurrentScope()) {
    onScopeDispose(() => {
      offValue()
      offError()
      offFocus()
      offComposing()
      instance.dispose()
    })
  }

  return {
    instance,
    value,
    error,
    focused,
    composing,
    mode: computed(() => instance.mode()),
    disabled: computed(() => field.effectiveDisabled),
    readonly: computed(() => field.value.readonly),
    required: computed(() => field.effectiveRequired),
    setValue: (next: T) => instance.write(next),
    commit: () => instance.commit(),
    clear: () => instance.clear(),
    focus: () => instance.focus(),
    blur: () => instance.blur(),
    compositionStart: () => instance.compositionStart(),
    compositionEnd: () => instance.compositionEnd(),
  }
}
