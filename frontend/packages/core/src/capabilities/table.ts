/**
 * 表格组件基类：表格数据 / 排序 / 选中 / 分页状态。
 */

import { BaseDataState } from './data-state'

/** 排序规格。 */
export interface SortSpec {
  /** 排序字段。 */
  field: string
  /** 方向。 */
  order: 'asc' | 'desc'
}

/** 表格组件基类（抽象）。 */
export abstract class BaseTable extends BaseDataState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'table'
  /** 行数据。 */
  rows: unknown[] = []
  /** 总条数。 */
  total = 0
  /** 页码。 */
  page = 1
  /** 页长（命名避开组件根尺寸档位 `size`）。 */
  pageSize = 20
  /** 当前排序。 */
  sort: SortSpec | undefined
  /** 选中行键。 */
  readonly selected = new Set<string | number>()

  /**
   * 设置行数据。
   *
   * @param rows 行数据。
   * @param total 总条数（缺省取行数）。
   */
  setRows(rows: readonly unknown[], total: number = rows.length): void {
    this.rows = [...rows]
    this.total = total
  }

  /**
   * 设置排序。
   *
   * @param field 字段。
   * @param order 方向。
   */
  sortBy(field: string, order: 'asc' | 'desc'): void {
    this.sort = { field, order }
  }

  /**
   * 切换行选中。
   *
   * @param key 行键。
   */
  toggleSelect(key: string | number): void {
    if (this.selected.has(key)) {
      this.selected.delete(key)
    } else {
      this.selected.add(key)
    }
  }

  /** 选中行键清单。 */
  get selectedKeys(): Array<string | number> {
    return [...this.selected]
  }
}
