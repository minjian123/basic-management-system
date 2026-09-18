/**
 * Vue 绑定：把 `BaseValue` 投影为组合式（响应式 `ref` + 变更订阅）。
 */

import { onScopeDispose, ref, type Ref } from 'vue'

import type { BaseValue } from '@bms/core'

/** `useValue` 返回面。 */
export interface UseValueResult<T> {
  /** 当前值（响应式）。 */
  value: Ref<T | undefined>
  /** 空态（响应式）。 */
  isEmpty: Ref<boolean>
  /** 设置值。 */
  setValue: (next: T | undefined) => void
}

/**
 * 投影值能力为组合式。
 *
 * @param source 值能力实例。
 * @returns 响应式值面（作用域销毁时自动取消订阅）。
 */
export function useValue<T>(source: BaseValue<T>): UseValueResult<T> {
  const value = ref(source.getSnapshot()) as Ref<T | undefined>
  const isEmpty = ref(source.isEmpty)
  const unsubscribe = source.onChange((next) => {
    value.value = next
    isEmpty.value = source.isEmpty
  })
  onScopeDispose(() => {
    unsubscribe()
  })
  return { value, isEmpty, setValue: (next) => source.setValue(next) }
}
