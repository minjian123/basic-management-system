/** 展示件投影：把核心展示组件基类 `BaseDisplay` 投影为组合式（值 / 空态）。 */

import { BaseDisplay } from '@bms/core'
import { onScopeDispose, ref, shallowRef, type Ref } from 'vue'

/** 具体展示件（可实例化）。 */
class DisplayState<T> extends BaseDisplay<T> {}

/** `useBaseDisplay` 返回面。 */
export interface UseBaseDisplayResult<T = unknown> {
  /** 展示基类实例。 */
  display: BaseDisplay<T>
  /** 当前值（响应式）。 */
  value: Ref<T | undefined>
  /** 是否空态（响应式）。 */
  isEmpty: Ref<boolean>
  /** 设置值。 */
  setValue: (value: T | undefined) => void
}

/**
 * 使用展示件投影。
 *
 * @returns 展示基类实例与响应式面。
 */
export function useBaseDisplay<T = unknown>(): UseBaseDisplayResult<T> {
  const display = new DisplayState<T>()
  const value = shallowRef<T | undefined>(display.value)
  const isEmpty = ref(display.isEmpty)

  display.onChange((next) => {
    value.value = next
  })
  const off = display.onLifecycle((event) => {
    if (event === 'update') {
      value.value = display.value
      isEmpty.value = display.isEmpty
    }
  })
  onScopeDispose(off)

  return {
    display,
    value,
    isEmpty,
    setValue: (next) => display.setValue(next),
  }
}
