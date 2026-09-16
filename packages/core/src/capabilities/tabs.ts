/** 页签状态能力：打开 / 关闭 / 固定 / 缓存键清单（多标签导航、双层 Tab、内容页签共用）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface TabEntry {
  key: string
  name?: string
  title?: string
  path?: string
  pinned?: boolean
  closable?: boolean
}

export interface TabsOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  maxOpen?: number
}

export class BaseTabs extends BaseCapability {
  readonly tabs = observable<readonly TabEntry[]>([])
  readonly activeKey = observable('')
  readonly maxOpen: number

  constructor(options: TabsOptions = {}) {
    super({ ...options, key: options.key ?? 'tabs' })
    this.maxOpen = Math.max(1, options.maxOpen ?? 12)
  }

  open(tab: TabEntry): void {
    const list = [...this.tabs.get()]
    const index = list.findIndex((item) => item.key === tab.key)
    if (index >= 0) {
      list[index] = { ...list[index], ...tab }
    } else {
      if (list.length >= this.maxOpen) {
        const victim = list.findIndex((item) => !item.pinned && item.closable !== false)
        if (victim >= 0) {
          list.splice(victim, 1)
        }
      }
      list.push(tab)
    }
    this.tabs.set(list)
    this.activeKey.set(tab.key)
  }

  close(key: string): void {
    const list = this.tabs.get()
    const target = list.find((item) => item.key === key)
    if (!target || target.pinned || target.closable === false) {
      return
    }
    const next = list.filter((item) => item.key !== key)
    this.tabs.set(next)
    if (this.activeKey.get() === key) {
      this.activeKey.set(next[next.length - 1]?.key ?? '')
    }
  }

  /** 缓存键清单（供 keep-alive 类消费） */
  get cachedNames(): string[] {
    return this.tabs.get().map((item) => item.name ?? item.key)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), maxOpen: this.maxOpen, count: this.tabs.get().length }
  }
}
