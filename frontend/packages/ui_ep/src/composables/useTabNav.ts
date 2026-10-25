/** 多标签导航组合式：页签打开 / 关闭 / 刷新 / keep-alive 名单 / 会话内持久化。状态经核心页签能力基类 `BaseTabs`。 */

import { BaseTabs } from '@bms/core'
import { ref, type Ref } from 'vue'

import { useBasePersistedState } from './useBasePersistedState'
import { useConfirm } from './useConfirm'

/** 页签项。 */
export interface TabNavItem {
  /** 唯一键（路由 `fullPath`）。 */
  key: string
  /** 标题。 */
  title: string
  /** 跳转路径。 */
  path: string
  /** 路由名。 */
  name?: string
  /** 图标名。 */
  icon?: string
  /** 是否可关闭（缺省 `true`）。 */
  closable?: boolean
  /** 是否脏数据（关闭前确认）。 */
  dirty?: boolean
  /** 是否参与 keep-alive 缓存（来自路由 `meta.keepAlive`）。 */
  keepAlive?: boolean
}

/** 选项。 */
export interface UseTabNavOptions {
  /** 持久化键（`sessionStorage`）。 */
  storageKey?: string
  /** 初始页签。 */
  initial?: TabNavItem[]
}

/** `useTabNav` 返回面。 */
export interface UseTabNavResult {
  /** 已打开页签。 */
  tabs: Ref<TabNavItem[]>
  /** 当前激活键。 */
  activeKey: Ref<string>
  /** keep-alive 名单（`keepAlive ∩ 已打开`）。 */
  cachedKeys: Ref<string[]>
  /** 正在刷新的页签键（宿主可据此重建视图）。 */
  refreshing: Ref<string>
  /** 打开 / 激活页签。 */
  open: (item: TabNavItem) => void
  /** 激活页签。 */
  activate: (key: string) => void
  /** 关闭页签（脏数据经二次确认；固定页签拒绝并返回 `false`）。 */
  close: (key: string) => Promise<boolean>
  /** 关闭其他（保留固定页签）。 */
  closeOthers: (key: string) => Promise<void>
  /** 关闭右侧（保留固定页签）。 */
  closeRight: (key: string) => Promise<void>
  /** 关闭全部（保留固定页签）。 */
  closeAll: () => Promise<void>
  /** 刷新页签（移除缓存以触发重建）。 */
  refresh: (key: string) => void
  /** 标记脏数据。 */
  markDirty: (key: string, dirty?: boolean) => void
}

/** 具体页签状态（可实例化）。 */
class TabNavState extends BaseTabs {
  /** 页签完整信息。 */
  readonly items = new Map<string, TabNavItem>()

  /** 固定页签键清单。 */
  get pinnedKeys(): string[] {
    return this.tabs.filter((tab) => tab.pinned === true).map((tab) => tab.key)
  }

  /** keep-alive 名单（按 `keepAlive` 过滤已打开页签）。 */
  cachedList(): string[] {
    return this.cacheKeys.filter((key) => this.items.get(key)?.keepAlive === true)
  }
}

/**
 * 使用多标签导航。
 *
 * @param options 选项。
 * @returns 页签状态与操作方法。
 */
export function useTabNav(options: UseTabNavOptions = {}): UseTabNavResult {
  const { confirm } = useConfirm()
  const storage = useBasePersistedState({ stateKey: options.storageKey ?? '', storage: 'session' })
  const state = new TabNavState()
  const tabs = ref<TabNavItem[]>([])
  const activeKey = ref('')
  const cachedKeys = ref<string[]>([])
  const refreshing = ref('')

  function persist(): void {
    if (options.storageKey === undefined) {
      return
    }
    storage.setLocal({ tabs: tabs.value, activeKey: activeKey.value })
    storage.persist()
  }

  function sync(): void {
    tabs.value = state.tabs.map((tab) => ({ ...(state.items.get(tab.key) as TabNavItem), key: tab.key, title: tab.title }))
    activeKey.value = state.activeKey ?? ''
    cachedKeys.value = state.cachedList()
  }

  state.onLifecycle((event) => {
    if (event === 'update') {
      sync()
      persist()
    }
  })

  function open(item: TabNavItem): void {
    state.items.set(item.key, item)
    state.open({ key: item.key, title: item.title, pinned: item.closable === false })
  }

  function activate(key: string): void {
    state.activate(key)
  }

  function markDirty(key: string, dirty = true): void {
    const item = state.items.get(key)
    if (item !== undefined) {
      item.dirty = dirty
      sync()
    }
  }

  async function close(key: string): Promise<boolean> {
    const item = state.items.get(key)
    if (item === undefined || item.closable === false) {
      return false
    }
    if (item.dirty === true) {
      const confirmed = await confirm({ content: '该页签存在未保存的修改，确定关闭吗？' })
      if (!confirmed) {
        return false
      }
    }
    state.close(key)
    state.items.delete(key)
    return true
  }

  async function closeKeys(keys: string[]): Promise<void> {
    for (const key of keys) {
      await close(key)
    }
  }

  async function closeOthers(key: string): Promise<void> {
    await closeKeys(state.cacheKeys.filter((item) => item !== key && !state.pinnedKeys.includes(item)))
  }

  async function closeRight(key: string): Promise<void> {
    const index = state.cacheKeys.indexOf(key)
    if (index < 0) {
      return
    }
    await closeKeys(state.cacheKeys.slice(index + 1).filter((item) => !state.pinnedKeys.includes(item)))
  }

  async function closeAll(): Promise<void> {
    await closeKeys(state.cacheKeys.filter((item) => !state.pinnedKeys.includes(item)))
  }

  function refresh(key: string): void {
    if (!state.cacheKeys.includes(key)) {
      return
    }
    refreshing.value = key
    cachedKeys.value = state.cachedList().filter((item) => item !== key)
    queueMicrotask(() => {
      refreshing.value = ''
      cachedKeys.value = state.cachedList()
    })
  }

  function restore(): void {
    const parsed = storage.restore() ? (storage.local.value as { tabs: TabNavItem[]; activeKey: string }) : undefined
    const source: TabNavItem[] = parsed?.tabs ?? options.initial ?? []
    const storedActive = parsed?.activeKey ?? ''
    for (const item of source) {
      open({ ...item, dirty: false })
    }
    if (storedActive !== '' && state.cacheKeys.includes(storedActive)) {
      state.activate(storedActive)
    }
    sync()
  }

  try {
    restore()
  } catch {
    state.items.clear()
    state.tabs.splice(0, state.tabs.length)
    sync()
  }

  return {
    tabs,
    activeKey,
    cachedKeys,
    refreshing,
    open,
    activate,
    close,
    closeOthers,
    closeRight,
    closeAll,
    refresh,
    markDirty,
  }
}
