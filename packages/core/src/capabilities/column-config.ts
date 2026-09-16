/** 列配置能力：显隐 / 顺序 / 宽度 / 冻结状态（持久化经 `persisted-state` 对接），依赖 `persisted-state`。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface ColumnMeta {
  key: string
  width?: number
  hidden?: boolean
  frozen?: boolean
}

export interface ColumnConfigOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  columns?: readonly ColumnMeta[]
}

export class BaseColumnConfig extends BaseCapability {
  readonly columns = observable<readonly ColumnMeta[]>([])

  constructor(options: ColumnConfigOptions = {}) {
    super({ ...options, key: options.key ?? 'column-config' })
    this.columns.set(options.columns ?? [])
  }

  toggleHidden(key: string): void {
    this.columns.set(
      this.columns.get().map((column) =>
        column.key === key ? { ...column, hidden: !column.hidden } : column,
      ),
    )
  }

  move(from: number, to: number, dragDrop: { reorder: <T>(list: readonly T[], from: number, to: number) => T[] }): void {
    this.columns.set(dragDrop.reorder(this.columns.get(), from, to))
  }

  /** 可见列（保序） */
  get visible(): readonly ColumnMeta[] {
    return this.columns.get().filter((column) => !column.hidden)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), count: this.columns.get().length }
  }
}
