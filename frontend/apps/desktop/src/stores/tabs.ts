/**
 * 表单框架页签 store（宿主侧状态）：列表 Tab（固定不可关）+ 记录 Tab（新增 / 双击行打开、可关）。
 *
 * 与 ui-ep `FormFrame` 件配套：件受控（`tabs` + `modelValue`），状态与脏数据拦截归本 store；
 * 关闭拦截口径——`close(key)` 对**脏页签**返回 false（由宿主提示确认后调 `discard(key)` 强关）。
 */

import { defineStore } from 'pinia'

/** 页签类型（列表 / 记录）。 */
export type TabType = 'list' | 'record'

/** 页签项。 */
export interface TabsTab {
  /** 页签键（唯一）。 */
  key: string
  /** 页签标题。 */
  title: string
  /** 页签类型。 */
  type: TabType
  /** 是否可关闭（列表页签固定不可关）。 */
  closable: boolean
  /** 是否存在未保存变更。 */
  dirty: boolean
}

/** 页签 store 状态。 */
interface TabsState {
  /** 页签清单（插入序；列表页签恒为首项）。 */
  tabs: TabsTab[]
  /** 当前激活页签键。 */
  active: string
}

/** 记录页签键前缀（`record:<实体主键>`）。 */
export const RECORD_TAB_PREFIX = 'record:'

/**
 * 记录页签键。
 *
 * @param key 实体主键。
 */
export function recordTabKey(key: string): string {
  return `${RECORD_TAB_PREFIX}${key}`
}

export const useTabsStore = defineStore('tabs', {
  state: (): TabsState => ({ tabs: [], active: '' }),
  getters: {
    /** 按键取页签（无则 `undefined`）。 */
    tabOf: (state) => {
      return (key: string): TabsTab | undefined => state.tabs.find((tab) => tab.key === key)
    },
    /** 当前激活页签（无则 `undefined`）。 */
    activeTab: (state): TabsTab | undefined => state.tabs.find((tab) => tab.key === state.active),
    /** 存在未保存变更的页签键清单。 */
    dirtyKeys: (state): string[] => state.tabs.filter((tab) => tab.dirty).map((tab) => tab.key),
  },
  actions: {
    /**
     * 重置为「仅列表页签」并激活列表。
     *
     * @param key 列表页签键。
     * @param title 列表页签标题。
     */
    reset(key: string, title: string): void {
      this.tabs = [{ key, title, type: 'list', closable: false, dirty: false }]
      this.active = key
    },
    /**
     * 打开记录页签（已存在则仅激活，不重置脏态）。
     *
     * @param key 页签键。
     * @param title 页签标题。
     */
    open(key: string, title: string): void {
      const existing = this.tabs.find((tab) => tab.key === key)
      if (existing === undefined) {
        this.tabs.push({ key, title, type: 'record', closable: true, dirty: false })
      }
      this.active = key
    },
    /**
     * 激活页签（不存在则忽略）。
     *
     * @param key 页签键。
     */
    activate(key: string): void {
      if (this.tabs.some((tab) => tab.key === key)) {
        this.active = key
      }
    },
    /**
     * 设置脏态。
     *
     * @param key 页签键。
     * @param dirty 是否脏。
     */
    setDirty(key: string, dirty: boolean): void {
      const tab = this.tabs.find((item) => item.key === key)
      if (tab !== undefined) {
        tab.dirty = dirty
      }
    },
    /**
     * 关闭页签（脏数据拦截：脏页签返回 false，由宿主确认后调 `discard`）。
     *
     * @param key 页签键。
     * @returns 是否已关闭。
     */
    close(key: string): boolean {
      const index = this.tabs.findIndex((tab) => tab.key === key)
      if (index < 0) {
        return false
      }
      const tab = this.tabs[index]
      if (tab === undefined || !tab.closable) {
        return false
      }
      if (tab.dirty) {
        return false
      }
      this.removeAt(index)
      return true
    },
    /**
     * 放弃变更并关闭页签（脏数据确认通过后调用）。
     *
     * @param key 页签键。
     * @returns 是否已关闭。
     */
    discard(key: string): boolean {
      const index = this.tabs.findIndex((tab) => tab.key === key)
      if (index < 0) {
        return false
      }
      const tab = this.tabs[index]
      if (tab === undefined || !tab.closable) {
        return false
      }
      tab.dirty = false
      this.removeAt(index)
      return true
    },
    /**
     * 移除指定位置页签并把激活键顺延到相邻页签。
     *
     * @param index 页签下标。
     */
    removeAt(index: number): void {
      const removed = this.tabs[index]
      this.tabs.splice(index, 1)
      if (removed === undefined || this.active !== removed.key) {
        return
      }
      const next = this.tabs[index] ?? this.tabs[index - 1]
      this.active = next?.key ?? ''
    },
  },
})
