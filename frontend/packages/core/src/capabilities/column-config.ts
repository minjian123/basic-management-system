/**
 * 列配置组件基类（列配置族）：显隐 / 顺序 / 宽度 / 冻结 / 持久化。
 */

import { BasePersistedState } from './persisted-state'

/** 列状态。 */
export interface ColumnState {
  /** 列键。 */
  key: string
  /** 是否可见。 */
  visible: boolean
  /** 顺序（自 0 起）。 */
  order: number
  /** 宽度。 */
  width?: number
  /** 是否冻结。 */
  frozen?: boolean
}

/** 列配置组件基类（抽象）。 */
export abstract class BaseColumnConfig extends BasePersistedState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'column-config'
  /** 列状态清单。 */
  readonly columns: ColumnState[] = []

  /**
   * 设置列状态（整体替换并写入本地持久化）。
   *
   * @param columns 列状态。
   */
  setColumns(columns: readonly ColumnState[]): void {
    this.columns.length = 0
    this.columns.push(...columns.map((column) => ({ ...column })))
    this.setLocal([...this.columns])
  }

  /**
   * 切换列显隐。
   *
   * @param key 列键。
   */
  toggleVisible(key: string): void {
    const column = this.columns.find((entry) => entry.key === key)
    if (column !== undefined) {
      column.visible = !column.visible
      this.setLocal([...this.columns])
    }
  }

  /** 可见列（按顺序）。 */
  get visibleColumns(): ColumnState[] {
    return this.columns.filter((column) => column.visible).sort((a, b) => a.order - b.order)
  }
}
