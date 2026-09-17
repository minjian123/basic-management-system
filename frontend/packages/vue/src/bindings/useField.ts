/**
 * 字段编排投影（Vue 绑定插件）：核心 `BaseField`（值 + 壳 + 权限）↔ Vue 响应式。
 */

import { computed, getCurrentScope, onScopeDispose, shallowRef, type ComputedRef, type ShallowRef } from 'vue'

import { createCapability, type BaseField, type FieldOptions } from '@bms/core'

export interface UseFieldReturn<T = unknown> {
  instance: BaseField<T>
  value: ShallowRef<T>
  error: ShallowRef<string>
  effectiveDisabled: ComputedRef<boolean>
  effectiveRequired: ComputedRef<boolean>
  setValue: (value: T) => void
  validate: () => boolean
}

export function useField<T = unknown>(options: FieldOptions<T> = {}): UseFieldReturn<T> {
  const instance = createCapability<BaseField<T>>('field', options)
  const value = shallowRef(instance.getValue())
  const error = shallowRef(instance.shell.error.get())

  const unsubscribeValue = instance.value.onChange((next) => {
    value.value = next
  })
  const unsubscribeError = instance.shell.error.subscribe((next) => {
    error.value = next
  })

  if (getCurrentScope()) {
    onScopeDispose(() => {
      unsubscribeValue()
      unsubscribeError()
      instance.dispose()
    })
  }

  return {
    instance,
    value,
    error,
    effectiveDisabled: computed(() => instance.effectiveDisabled),
    effectiveRequired: computed(() => instance.effectiveRequired),
    setValue: (next: T) => instance.setValue(next),
    validate: () => instance.validate(),
  }
}
