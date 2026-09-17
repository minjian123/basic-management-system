/**
 * 应用标签状态（S5a 试点切流）：`@bms/vue` 的 `useTabs`（核心 `BaseTabs`）→ 宿主标签栏。
 *
 * 模块级 `effectScope` 单例（跨布局重挂载保持）；批量关闭（关其他 / 关右侧 / 全关）按
 * 旧标签栏语义组合实现（保留固定签与不可关项；关闭激活签由核心迁移激活）。
 */

import { effectScope } from 'vue'

import { useTabs, type TabItem } from '@bms/vue'

export interface AppTabsReturn {
  readonly tabs: readonly TabItem[]
  readonly activeKey: string
  readonly cachedNames: string[]
  open: (tab: TabItem) => void
  activate: (key: string) => void
  close: (key: string) => void
  closeOthers: (key: string) => void
  closeRight: (key: string) => void
  closeAll: () => void
}

const scope = effectScope(true)
const tabs = scope.run(() => useTabs({ maxOpen: 12 }))!

const closable = (item: TabItem): boolean => !item.pinned && item.closable !== false

/** 清空标签栏状态（测试隔离 / 登出重置） */
export function resetAppTabs(): void {
  for (const item of [...tabs.tabs]) {
    tabs.close(item.key)
  }
}

export function useAppTabs(): AppTabsReturn {
  return {
    get tabs() {
      return tabs.tabs
    },
    get activeKey() {
      return tabs.activeKey
    },
    get cachedNames() {
      return tabs.cachedNames
    },
    open: (tab) => tabs.open(tab),
    activate: (key) => tabs.activate(key),
    close: (key) => tabs.close(key),
    closeOthers: (key) => {
      for (const item of [...tabs.tabs]) {
        if (item.key !== key && closable(item)) {
          tabs.close(item.key)
        }
      }
    },
    closeRight: (key) => {
      const list = tabs.tabs
      const index = list.findIndex((item) => item.key === key)
      if (index < 0) {
        return
      }
      for (const item of list.slice(index + 1)) {
        if (closable(item)) {
          tabs.close(item.key)
        }
      }
    },
    closeAll: () => {
      for (const item of [...tabs.tabs]) {
        if (closable(item)) {
          tabs.close(item.key)
        }
      }
    },
  }
}
