/** 偏好持久化投影：把核心偏好持久化能力基类 `BasePersistedState` 投影为组合式（本地即时状态 / 远端版本）。 */

import { BasePersistedState } from '@bms/core'
import { onScopeDispose, ref, shallowRef, type Ref } from 'vue'

/** 具体持久化状态（可实例化）。 */
class PersistedState extends BasePersistedState {}

/** 选项。 */
export interface UseBasePersistedStateOptions {
  /** 状态键（本地 / 远端一致）。 */
  stateKey?: string
  /** 初始本地状态。 */
  initial?: unknown
}

/** `useBasePersistedState` 返回面。 */
export interface UseBasePersistedStateResult {
  /** 持久化基类实例。 */
  persisted: BasePersistedState
  /** 本地即时状态（响应式）。 */
  local: Ref<unknown>
  /** 远端版本号（响应式）。 */
  remoteVersion: Ref<number>
  /** 写入本地即时状态。 */
  setLocal: (value: unknown) => void
  /** 设置远端版本号。 */
  setRemoteVersion: (version: number) => void
  /** 是否需要按远端版本刷新。 */
  needsRemoteRefresh: (version: number) => boolean
  /** 加载远端偏好（占位：返回本地快照）。 */
  loadRemote: () => Promise<unknown>
}

/**
 * 使用偏好持久化投影。
 *
 * @param options 选项。
 * @returns 持久化基类实例与响应式面。
 */
export function useBasePersistedState(options: UseBasePersistedStateOptions = {}): UseBasePersistedStateResult {
  const persisted = new PersistedState()
  if (options.stateKey !== undefined) {
    persisted.stateKey = options.stateKey
  }
  if (options.initial !== undefined) {
    persisted.setLocal(options.initial)
  }

  const local = shallowRef<unknown>(persisted.local)
  const remoteVersion = ref(persisted.remoteVersion)
  const off = persisted.onLifecycle((event) => {
    if (event === 'update') {
      local.value = persisted.local
      remoteVersion.value = persisted.remoteVersion
    }
  })
  onScopeDispose(off)

  return {
    persisted,
    local,
    remoteVersion,
    setLocal: (value) => persisted.setLocal(value),
    setRemoteVersion: (version) => {
      persisted.remoteVersion = version
      persisted.notifyLifecycle('update')
    },
    needsRemoteRefresh: (version) => persisted.needsRemoteRefresh(version),
    loadRemote: () => persisted.loadRemote(),
  }
}
