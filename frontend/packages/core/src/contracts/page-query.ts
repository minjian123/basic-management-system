/**
 * 分页查询契约：页码 / 页长 / 排序 / 筛选（与后端分页契约口径一致）。
 */

import { BaseDataObject } from './data-object'

/** 排序方向。 */
export type SortOrder = 'asc' | 'desc'

/** 分页查询基类。 */
export class BasePageQuery extends BaseDataObject {
  /** 页码（自 1 起）。 */
  page = 1
  /** 页长。 */
  size = 20
  /** 排序字段。 */
  orderBy?: string
  /** 排序方向。 */
  order?: SortOrder

  /** 偏移量（页码换算）。 */
  get offset(): number {
    return (this.page - 1) * this.size
  }
}
