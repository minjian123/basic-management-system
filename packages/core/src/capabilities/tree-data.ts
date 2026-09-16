/** 树数据能力：展开 / 选中 / 勾选骨架（加载与懒加载经注入 loader 承担）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface TreeNodeLike {
  key: string
  children?: readonly TreeNodeLike[]
}

export interface TreeDataOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  multiple?: boolean
  checkable?: boolean
}

export class BaseTreeData extends BaseCapability {
  readonly expanded = observable<readonly string[]>([])
  readonly selected = observable<readonly string[]>([])
  readonly checked = observable<readonly string[]>([])
  readonly multiple: boolean
  readonly checkable: boolean

  constructor(options: TreeDataOptions = {}) {
    super({ ...options, key: options.key ?? 'tree-data' })
    this.multiple = options.multiple ?? false
    this.checkable = options.checkable ?? false
  }

  toggleExpand(key: string): void {
    const list = this.expanded.get()
    this.expanded.set(list.includes(key) ? list.filter((item) => item !== key) : [...list, key])
  }

  select(key: string): void {
    if (!this.multiple) {
      this.selected.set([key])
      return
    }
    const list = this.selected.get()
    this.selected.set(list.includes(key) ? list.filter((item) => item !== key) : [...list, key])
  }

  toggleCheck(key: string): void {
    if (!this.checkable) {
      return
    }
    const list = this.checked.get()
    this.checked.set(list.includes(key) ? list.filter((item) => item !== key) : [...list, key])
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), multiple: this.multiple, checkable: this.checkable }
  }
}
