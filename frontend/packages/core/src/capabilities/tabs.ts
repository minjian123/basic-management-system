/**
 * 页签状态能力基类：打开 / 关闭 / 固定 / 缓存键清单。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 页签项。 */
export interface TabItem {
  /** 唯一键。 */
  key: string
  /** 标题。 */
  title: string
  /** 是否固定。 */
  pinned?: boolean
}

/** 页签能力基类（抽象）。 */
export abstract class BaseTabs extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'tabs'
  /** 已打开页签（保序）。 */
  readonly tabs: TabItem[] = []
  /** 当前激活页签键。 */
  activeKey: string | undefined

  /**
   * 打开页签（已存在则激活）。
   *
   * @param tab 页签项。
   */
  open(tab: TabItem): void {
    if (!this.tabs.some((item) => item.key === tab.key)) {
      this.tabs.push({ ...tab })
    }
    this.activeKey = tab.key
    this.notifyLifecycle('update')
  }

  /**
   * 关闭页签（激活相邻：右 → 左）。
   *
   * @param key 页签键。
   */
  close(key: string): void {
    const index = this.tabs.findIndex((item) => item.key === key)
    if (index < 0) {
      return
    }
    this.tabs.splice(index, 1)
    if (this.activeKey === key) {
      this.activeKey = (this.tabs[index] ?? this.tabs[index - 1])?.key
    }
    this.notifyLifecycle('update')
  }

  /**
   * 固定 / 取消固定页签。
   *
   * @param key 页签键。
   * @param pinned 是否固定。
   */
  pin(key: string, pinned = true): void {
    const tab = this.tabs.find((item) => item.key === key)
    if (tab === undefined) {
      return
    }
    tab.pinned = pinned
    this.notifyLifecycle('update')
  }

  /**
   * 激活页签。
   *
   * @param key 页签键。
   */
  activate(key: string): void {
    if (!this.tabs.some((item) => item.key === key)) {
      return
    }
    this.activeKey = key
    this.notifyLifecycle('update')
  }

  /** 缓存键清单（已打开页签键，供 keep-alive）。 */
  get cacheKeys(): string[] {
    return this.tabs.map((item) => item.key)
  }
}
