/**
 * 受控值投影（Vue 绑定插件）：核心 `BaseValue` 实例 ↔ Vue 响应式。
 *
 * 口径：**组合式只存在于插件层**——实例化 / 取用核心能力，把核心可订阅状态投影为 `ref`；
 * 卸载（scope 停止）时取消订阅并释放核心实例。
 */

import { getCurrentScope, onScopeDispose, shallowRef, type ShallowRef } from 'vue'

import { createCapability, type BaseValue, type ValueOptions } from '@bms/core'

export interface UseValueReturn<T = unknown> {
  /** 核心能力实例（单一来源） */
  instance: BaseValue<T>
  /** 投影的响应式值 */
  value: ShallowRef<T>
  setValue: (value: T) => void
  readonly isEmpty: () => boolean
}

export function useValue<T = unknown>(options: ValueOptions<T> = {}): UseValueReturn<T> {
  const instance = createCapability<BaseValue<T>>('value', options)
  const value = shallowRef(instance.getValue())
  const unsubscribe = instance.onChange((next) => {
    value.value = next
  })

  if (getCurrentScope()) {
    onScopeDispose(() => {
      unsubscribe()
      instance.dispose()
    })
  }

  return {
    instance,
    value,
    setValue: (next: T) => instance.setValue(next),
    isEmpty: () => instance.isEmpty,
  }
}
