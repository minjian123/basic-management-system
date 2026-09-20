/**
 * 列配置组件基类（列配置族）：显隐 / 顺序 / 宽度 / 冻结 / 持久化。
 *
 * 列状态为**权威**；顺序与宽度属偏好内容（可持久化），冻结为会话态（不持久化）。
 */

import { BasePersistedState } from './persisted-state'

import { clampColumnWidth } from '../domain/table'

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

/** 列种子（声明式列或元数据列的归一形态）。 */
export interface ColumnSeed {
  /** 列键。 */
  key: string
  /** 宽度。 */
  width?: number
  /** 是否可见。 */
  visible?: boolean
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

  /**
   * 设置列显隐（末列不可隐藏，保证至少保留一列）。
   *
   * @param key 列键。
   * @param visible 是否可见。
   */
  setVisible(key: string, visible: boolean): void {
    const column = this.columns.find((entry) => entry.key === key)
    if (column === undefined || column.visible === visible) {
      return
    }
    if (!visible && this.columns.filter((entry) => entry.visible).length <= 1) {
      return
    }
    column.visible = visible
    this.setLocal([...this.columns])
  }

  /**
   * 设置列宽（夹取到下限）。
   *
   * @param key 列键。
   * @param width 宽度。
   */
  setWidth(key: string, width: number): void {
    const column = this.columns.find((entry) => entry.key === key)
    if (column === undefined) {
      return
    }
    const next = clampColumnWidth(width)
    if (column.width === next) {
      return
    }
    column.width = next
    this.setLocal([...this.columns])
  }

  /**
   * 设置列冻结（会话态，不写入持久化）。
   *
   * @param key 列键。
   * @param frozen 是否冻结。
   */
  setFrozen(key: string, frozen: boolean): void {
    const column = this.columns.find((entry) => entry.key === key)
    if (column === undefined || (column.frozen ?? false) === frozen) {
      return
    }
    column.frozen = frozen
    this.setLocal([...this.columns])
  }

  /**
   * 移动列（按偏移移动并重排顺序，偏移越界夹取）。
   *
   * @param key 列键。
   * @param offset 偏移（正数下移）。
   */
  moveColumn(key: string, offset: number): void {
    const index = this.columns.findIndex((column) => column.key === key)
    if (index < 0 || !Number.isFinite(offset)) {
      return
    }
    const target = Math.min(this.columns.length - 1, Math.max(0, index + Math.trunc(offset)))
    if (target === index) {
      return
    }
    const [moved] = this.columns.splice(index, 1)
    if (moved === undefined) {
      return
    }
    this.columns.splice(target, 0, moved)
    this.columns.forEach((column, order) => {
      column.order = order
    })
    this.setLocal([...this.columns])
  }

  /**
   * 与列种子归一（保留既有列显隐 / 宽度 / 相对顺序，剔除已删列，追加新增列）。
   *
   * @param seeds 列种子。
   */
  normalizeWith(seeds: readonly ColumnSeed[]): void {
    const seedKeys = new Set(seeds.map((seed) => seed.key))
    const kept = this.columns.filter((column) => seedKeys.has(column.key))
    const keptKeys = new Set(kept.map((column) => column.key))
    const added: ColumnState[] = seeds
      .filter((seed) => !keptKeys.has(seed.key))
      .map((seed) => ({ key: seed.key, visible: seed.visible !== false, order: 0, width: seed.width, frozen: false }))
    const next = [...kept, ...added].map((column, index) => ({
      key: column.key,
      visible: column.visible,
      order: index,
      width: column.width,
      frozen: false,
    }))
    this.columns.length = 0
    this.columns.push(...next)
    this.setLocal([...this.columns])
  }

  /**
   * 恢复默认（按列种子全量重建，显隐 / 顺序 / 宽度回声明默认）。
   *
   * @param seeds 列种子。
   */
  resetColumns(seeds: readonly ColumnSeed[]): void {
    this.columns.length = 0
    this.columns.push(
      ...seeds.map((seed, index) => ({
        key: seed.key,
        visible: seed.visible !== false,
        order: index,
        width: seed.width,
        frozen: seed.frozen ?? false,
      })),
    )
    this.setLocal([...this.columns])
  }

  /** 可见列（按顺序）。 */
  get visibleColumns(): ColumnState[] {
    return this.columns.filter((column) => column.visible).sort((a, b) => a.order - b.order)
  }

  /** 可见列键（按顺序）。 */
  get visibleOrder(): string[] {
    return this.visibleColumns.map((column) => column.key)
  }

  /**
   * 是否已含某列。
   *
   * @param key 列键。
   */
  has(key: string): boolean {
    return this.columns.some((column) => column.key === key)
  }
}
