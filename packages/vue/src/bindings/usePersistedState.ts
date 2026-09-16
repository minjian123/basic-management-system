/**
 * 偏好持久化投影（Vue 绑定插件）：核心 `BasePersistedState` ↔ Vue。
 *
 * 接口面与旧片段同构（`state` / `syncing` / `synced` / `isPlaceholder` / `get` / `set` / `reset` /
 * `syncFromRemote` / `flush`）——远端同步为**占位**（不发请求；真实偏好接口随认证 / 个人中心任务接入）。
 */

import { getCurrentScope, onScopeDispose, shallowRef } from 'vue'

import { createCapability, type BasePersistedState } from '@bms/core'

export interface UsePersistedStateOptions<T = unknown> {
  /** 偏好键 */
  key: string
  /** 作用域（占位兼容：核心暂不区分 scope，键由调用方拼接） */
  scope?: unknown
  defaultValue: T
  /** 远端同步防抖（占位兼容，未启用） */
  syncDebounce?: unknown
  /** 本地与远端合并器（占位兼容，未启用） */
  merge?: unknown
  /** 远端适配器（缺省占位：不请求） */
  remote?: unknown
}

export interface UsePersistedStateReturn<T = unknown> {
  readonly state: T
  readonly syncing: boolean
  readonly synced: boolean
  /** 占位态：远端偏好接口未接入 */
  readonly isPlaceholder: boolean
  get: () => T
  set: (value: T) => void
  reset: () => void
  syncFromRemote: () => Promise<T>
  flush: () => Promise<void>
}

export function usePersistedState<T = unknown>(
  options: UsePersistedStateOptions<T>,
): UsePersistedStateReturn<T> {
  const instance = createCapability<BasePersistedState<T>>('persisted-state', {
    prefKey: options.key,
    defaultValue: options.defaultValue,
  })
  const state = shallowRef(instance.get())
  const unsubscribe = instance.state.subscribe((next) => {
    state.value = next
  })

  if (getCurrentScope()) {
    onScopeDispose(() => {
      unsubscribe()
      instance.dispose()
    })
  }

  return {
    get state() {
      return state.value
    },
    get syncing() {
      return false
    },
    get synced() {
      return false
    },
    get isPlaceholder() {
      return true
    },
    get: () => instance.get(),
    set: (value: T) => instance.set(value),
    reset: () => instance.reset(options.defaultValue),
    syncFromRemote: async () => instance.get(),
    flush: async () => {},
  }
}
