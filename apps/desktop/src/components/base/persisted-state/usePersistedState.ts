/**
 * 偏好持久化片段（`persisted-state`）：本地即时生效 + 远端偏好同步。
 *
 * 契约见《组件设计 · 偏好持久化片段》：`get` / `set` / `reset` / `syncFromRemote` / `flush` +
 * `state` / `syncing` / `synced`（`sys_user_preference` / `sys_query_scheme`；列配置、查询方案、
 * 偏好面板、主题语言共用）。**占位先行**：未注入 `remote`（偏好接口未接入）时只走本地存储，
 * `isPlaceholder` 标记，远端同步静默跳过（不请求、不报错）。
 */

import { computed, ref, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 远端同步接口（后端偏好接口接入后注入） */
export interface PreferenceRemoteAdapter {
  load: (key: string, scope?: string) => Promise<unknown>
  save: (key: string, value: unknown, scope?: string) => Promise<void>
  remove?: (key: string, scope?: string) => Promise<void>
}

/** 偏好持久化片段参数 */
export interface UsePersistedStateOptions<T = unknown> {
  /** 偏好键（含 scope 时形如 `column-config` / `query-scheme`） */
  key: string
  /** 作用域（多租户 / 多模块区分；缺省全局） */
  scope?: MaybeRefOrGetter<string | undefined>
  defaultValue: T
  /** 远端同步防抖（毫秒，默认 800） */
  syncDebounce?: MaybeRefOrGetter<number>
  /** 本地与远端值的合并器（缺省远端优先，对象做浅合并） */
  merge?: (local: T, remote: T) => T
  /** 远端适配器（缺省即占位：不请求） */
  remote?: PreferenceRemoteAdapter
}

/** 偏好持久化片段返回值 */
export interface UsePersistedStateReturn<T = unknown> {
  readonly state: T
  readonly syncing: boolean
  readonly synced: boolean
  /** 占位态：远端偏好接口未接入 */
  readonly isPlaceholder: boolean
  get: () => T
  /** 设置并即时落本地 + 防抖同步远端 */
  set: (value: T) => void
  reset: () => void
  /** 主动从远端拉取并合并 */
  syncFromRemote: () => Promise<T>
  /** 立即把待同步值写远端 */
  flush: () => Promise<void>
}

/** 本地存储键（含 scope） */
function storageKey(key: string, scope?: string): string {
  return scope ? `bms:pref:${scope}:${key}` : `bms:pref:${key}`
}

/** 读写本地存储（非浏览器环境静默跳过） */
function readLocal<T>(key: string): T | undefined {
  if (typeof localStorage === 'undefined') {
    return undefined
  }
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : undefined
  } catch {
    return undefined
  }
}

function writeLocal(key: string, value: unknown): void {
  if (typeof localStorage === 'undefined') {
    return
  }
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 隐私模式 / 配额不足：本地落盘失败不影响内存态
  }
}

/**
 * 获取偏好持久化能力。
 *
 * 用法：`const pref = usePersistedState({ key: 'column-config', defaultValue: [], remote })`；
 * 远端未接入时省略 `remote` 即得「本地即时生效 + 远端占位」行为。
 */
export function usePersistedState<T = unknown>(options: UsePersistedStateOptions<T>): UsePersistedStateReturn<T> {
  const capability = declareFragment('persisted-state')

  const scope = computed(() => toValue(options.scope))
  const key = computed(() => storageKey(options.key, scope.value))
  const isPlaceholder = computed(() => options.remote === undefined)
  const syncing = ref(false)
  const synced = ref(false)

  const initial = readLocal<T>(key.value) ?? options.defaultValue
  // 泛型偏好值用 `shallowRef`：避免深度解包改变业务对象形状
  const state = shallowRef<T>(initial)
  let timer: ReturnType<typeof setTimeout> | undefined
  let pending: T | undefined

  // 作用域变化（如切换租户）：重读本地值，避免串数据
  watch(key, (next) => {
    state.value = readLocal<T>(next) ?? options.defaultValue
    synced.value = false
  })

  const persistLocal = (value: T): void => {
    state.value = value
    writeLocal(key.value, value)
  }

  const flush = async (): Promise<void> => {
    if (!options.remote || pending === undefined) {
      return
    }
    syncing.value = true
    try {
      await options.remote.save(options.key, pending, scope.value)
      synced.value = true
      pending = undefined
    } catch (error) {
      capability.reportError(error, { scope: 'persisted-state.flush', key: options.key })
    } finally {
      syncing.value = false
    }
  }

  const scheduleSync = (): void => {
    if (!options.remote) {
      return
    }
    if (timer !== undefined) {
      clearTimeout(timer)
    }
    timer = setTimeout(
      () => {
        void flush()
      },
      Number(toValue(options.syncDebounce) ?? 800),
    )
  }

  return {
    get state() {
      return state.value
    },
    get syncing() {
      return syncing.value
    },
    get synced() {
      return synced.value
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get: () => state.value,
    set: (value) => {
      persistLocal(value)
      pending = value
      synced.value = false
      scheduleSync()
    },
    reset: () => {
      persistLocal(options.defaultValue)
      pending = options.defaultValue
      synced.value = false
      scheduleSync()
    },
    syncFromRemote: async () => {
      if (!options.remote) {
        capability.log('debug', 'persisted-state 占位：远端偏好接口未接入，跳过同步')
        return state.value
      }
      syncing.value = true
      try {
        const remote = await options.remote.load(options.key, scope.value)
        const local = state.value
        const merged =
          options.merge && remote !== undefined && remote !== null
            ? options.merge(local, remote as T)
            : ((remote ?? local) as T)
        persistLocal(merged)
        synced.value = true
        return merged
      } catch (error) {
        capability.reportError(error, { scope: 'persisted-state.sync', key: options.key })
        return state.value
      } finally {
        syncing.value = false
      }
    },
    flush,
  }
}
