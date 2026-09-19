/** 偏好持久化投影：把核心偏好持久化能力基类 `BasePersistedState` 投影为组合式（本地即时 / 本地存储 / 快照回滚 / 保存）。 */

import { BasePersistedState, type PersistedRemoteSaver, type PersistedStorage } from '@bms/core'
import { onScopeDispose, ref, shallowRef, type Ref } from 'vue'

/** 存储后端口径：`local` / `session` 取全局存储；也可直接注入存储实现（不可用时降级为不落盘）。 */
export type PersistedStorageOption = 'local' | 'session' | PersistedStorage

/** 具体持久化状态（可实例化）。 */
class PersistedState extends BasePersistedState {}

/** 选项。 */
export interface UseBasePersistedStateOptions {
  /** 状态键（本地 / 远端一致）。 */
  stateKey?: string
  /** 初始本地状态（仅当本地存储无值时生效）。 */
  initial?: unknown
  /** 存储后端（缺省 `local`）。 */
  storage?: PersistedStorageOption
  /** 远端保存注入点（未注入时保存只写本地并置待同步标记）。 */
  remoteSaver?: PersistedRemoteSaver
  /** 是否初始化时从本地存储恢复（缺省 `true`）。 */
  restore?: boolean
  /** 防抖保存毫秒（大于 0 时启用 `saveDebounced`，缺省 `0` 表示同步保存）。 */
  saveDelay?: number
}

/** `useBasePersistedState` 返回面。 */
export interface UseBasePersistedStateResult {
  /** 持久化基类实例。 */
  persisted: BasePersistedState
  /** 本地即时状态（响应式）。 */
  local: Ref<unknown>
  /** 远端版本号（响应式）。 */
  remoteVersion: Ref<number>
  /** 是否已有本地状态。 */
  hasLocal: Ref<boolean>
  /** 是否有未保存变更（与快照比较）。 */
  dirty: Ref<boolean>
  /** 远端待同步标记。 */
  pendingSync: Ref<boolean>
  /** 写入本地即时状态。 */
  setLocal: (value: unknown) => void
  /** 设置远端版本号。 */
  setRemoteVersion: (version: number) => void
  /** 是否需要按远端版本刷新。 */
  needsRemoteRefresh: (version: number) => boolean
  /** 加载远端偏好（占位：返回本地快照）。 */
  loadRemote: () => Promise<unknown>
  /** 从本地存储恢复。 */
  restore: () => boolean
  /** 写入本地存储。 */
  persist: () => boolean
  /** 记录快照。 */
  snapshot: () => void
  /** 回滚到快照。 */
  rollback: () => boolean
  /** 清空状态（内存 + 存储 + 快照）。 */
  clear: () => void
  /** 以默认值重置并保存。 */
  reset: (defaults: unknown) => Promise<boolean>
  /** 保存（本地 + 远端）。 */
  save: () => Promise<boolean>
  /** 防抖保存（`saveDelay` 为 0 时等同 `save`）。 */
  saveDebounced: () => void
}

/**
 * 解析存储后端（全局存储缺失或受限时返回 `undefined`）。
 *
 * @param option 存储后端口径。
 * @returns 存储实现或 `undefined`。
 */
function resolveStorage(option: PersistedStorageOption | undefined): PersistedStorage | undefined {
  if (option === undefined || option === 'local' || option === 'session') {
    const scope = globalThis as { localStorage?: PersistedStorage; sessionStorage?: PersistedStorage }
    return option === 'session' ? scope.sessionStorage : scope.localStorage
  }
  return option
}

/**
 * 使用偏好持久化投影。
 *
 * @param options 选项。
 * @returns 持久化基类实例与响应式面。
 */
export function useBasePersistedState(options: UseBasePersistedStateOptions = {}): UseBasePersistedStateResult {
  const persisted = new PersistedState()
  const storage = resolveStorage(options.storage)
  if (storage !== undefined) {
    persisted.storage = storage
  }
  if (options.remoteSaver !== undefined) {
    persisted.remoteSaver = options.remoteSaver
  }
  if (options.stateKey !== undefined) {
    persisted.stateKey = options.stateKey
  }
  if (options.restore !== false) {
    persisted.restore()
  }
  if (options.initial !== undefined && !persisted.hasLocal) {
    persisted.setLocal(options.initial)
  }

  const local = shallowRef<unknown>(persisted.local)
  const remoteVersion = ref(persisted.remoteVersion)
  const hasLocal = ref(persisted.hasLocal)
  const dirty = ref(persisted.dirty)
  const pendingSync = ref(persisted.pendingSync)

  /** 从基类实例同步响应式面（含 `pendingSync` 等非生命周期字段）。 */
  const sync = (): void => {
    local.value = persisted.local
    remoteVersion.value = persisted.remoteVersion
    hasLocal.value = persisted.hasLocal
    dirty.value = persisted.dirty
    pendingSync.value = persisted.pendingSync
  }

  const off = persisted.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  let timer: ReturnType<typeof setTimeout> | undefined
  /** 清理未触发的防抖定时器。 */
  const clearTimer = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
  }
  onScopeDispose(clearTimer)

  return {
    persisted,
    local,
    remoteVersion,
    hasLocal,
    dirty,
    pendingSync,
    setLocal: (value) => {
      persisted.setLocal(value)
      sync()
    },
    setRemoteVersion: (version) => {
      persisted.remoteVersion = version
      persisted.notifyLifecycle('update')
      sync()
    },
    needsRemoteRefresh: (version) => persisted.needsRemoteRefresh(version),
    loadRemote: () => persisted.loadRemote(),
    restore: () => {
      const restored = persisted.restore()
      sync()
      return restored
    },
    persist: () => {
      const written = persisted.persist()
      sync()
      return written
    },
    snapshot: () => {
      persisted.snapshot()
      sync()
    },
    rollback: () => {
      const rolled = persisted.rollback()
      sync()
      return rolled
    },
    clear: () => {
      clearTimer()
      persisted.clear()
      sync()
    },
    reset: async (defaults) => {
      const saved = await persisted.reset(defaults)
      sync()
      return saved
    },
    save: async () => {
      clearTimer()
      const saved = await persisted.save()
      sync()
      return saved
    },
    saveDebounced: () => {
      const delay = options.saveDelay ?? 0
      if (delay <= 0) {
        void persisted.save().then(sync)
        return
      }
      clearTimer()
      timer = setTimeout(() => {
        timer = undefined
        void persisted.save().then(sync)
      }, delay)
    },
  }
}
