/**
 * 表格组件基类：数据 / 分页 / 多列排序 / 组合多选与列配置 / 树形 / 展开 / 行内编辑。
 *
 * 组合 `BaseSelection`（多选权威）与 `BaseColumnConfig`（列状态权威）——**组合而非继承**
 * （体系唯一多重继承项为错误基座）；两者各在自身继承链上，链外不挂接功能。
 */

import { BaseColumnConfig } from './column-config'
import { BaseDataState } from './data-state'
import { BaseSelection } from './selection'

import {
  PAGE_SIZE_DEFAULT,
  PAGE_SIZE_MAX,
  buildSortParams,
  collectTreeKeys,
  resolveDensityToken,
  rowKeyOf,
  toggleSort as toggleColumnSort,
  type TableColumn,
  type TableDensity,
  type TableSortParams,
  type TableSortSpec,
} from '../domain/table'

/** 排序规格（字段 + 方向）。 */
export type SortSpec = TableSortSpec

/** 表格内置选中集合实现（组合用；继承链归属 `BaseSelection`）。 */
class TableSelection extends BaseSelection {}

/** 表格内置列状态实现（组合用；继承链归属 `BaseColumnConfig`）。 */
class TableColumnState extends BaseColumnConfig {}

/** 表格组件基类（抽象）。 */
export abstract class BaseTable extends BaseDataState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'table'
  /** 依赖登记（组合多选与列配置，故一并声明）。 */
  override readonly depends: readonly string[] = ['data-state', 'selection', 'column-config']
  /** 行数据。 */
  rows: unknown[] = []
  /** 总条数。 */
  total = 0
  /** 页码。 */
  page = 1
  /** 页长（命名避开组件根尺寸档位 `size`）。 */
  pageSize = PAGE_SIZE_DEFAULT
  /** 行主键字段。 */
  rowKey = 'id'
  /** 主排序（单列；多列排序见 `sorts`）。 */
  sort: SortSpec | undefined
  /** 多列排序（最多 3 列）。 */
  readonly sorts: SortSpec[] = []
  /** 列表密度档位（持久化取值口径；组件根 `density` 为 `DensityToken`，二者经 `densityToken` 映射）。 */
  listDensity: TableDensity = 'default'
  /** 多选（权威：跨页全选 / 汇总 / 模式）。 */
  readonly selection: BaseSelection = new TableSelection()
  /** 列状态（权威：显隐 / 顺序 / 宽度 / 冻结）。 */
  readonly columnConfig: BaseColumnConfig = new TableColumnState()
  /** 是否树形模式。 */
  tree = false
  /** 子节点字段。 */
  childrenKey = 'children'
  /** 已展开行键。 */
  readonly expandedKeys = new Set<string | number>()
  /** 是否行内编辑模式。 */
  editable = false

  /** 选中键集合（兼容垫片：只读快照；新代码用 `selection`）。 */
  get selected(): ReadonlySet<string | number> {
    return new Set<string | number>(this.selection.selected)
  }

  /** 选中行键清单（兼容垫片：键统一字符串;新代码用 `selection.selected`）。 */
  get selectedKeys(): string[] {
    return this.selection.selected.map((key) => String(key))
  }

  /**
   * 设置行数据（同步当前页行键与总条数）。
   *
   * @param rows 行数据。
   * @param total 总条数（缺省取行数）。
   */
  setRows(rows: readonly unknown[], total: number = rows.length): void {
    this.rows = [...rows]
    this.total = total
    this.selection.setTotal(total)
    this.selection.setPageKeys(this.rows.map((row) => rowKeyOf(row, this.rowKey)))
    this.notify()
  }

  /**
   * 设置单列排序（兼容保留；多列排序走 `toggleSort`）。
   *
   * @param field 字段。
   * @param order 方向。
   */
  sortBy(field: string, order: 'asc' | 'desc'): void {
    this.sort = { field, order }
    this.sorts.length = 0
    this.sorts.push({ field, order })
    this.notify()
  }

  /**
   * 切换排序（非叠加单列、叠加多列 ≤ 3）。
   *
   * @param column 目标列。
   * @param additive 是否叠加（Shift 点击）。
   * @returns 新排序列表。
   */
  toggleSort(column: TableColumn, additive = false): SortSpec[] {
    const next = toggleColumnSort(this.sorts, column, additive)
    this.sorts.length = 0
    this.sorts.push(...next)
    this.sort = this.sorts[0]
    this.notify()
    return [...this.sorts]
  }

  /** 清空排序。 */
  clearSort(): void {
    if (this.sorts.length === 0 && this.sort === undefined) {
      return
    }
    this.sorts.length = 0
    this.sort = undefined
    this.notify()
  }

  /** 排序参数（`order_by` 逗号分隔 + `order` 方向数组）。 */
  sortParams(): TableSortParams {
    return buildSortParams(this.sorts)
  }

  /**
   * 设置页码（自 1 起）。
   *
   * @param page 页码。
   */
  setPage(page: number): void {
    const next = Number.isFinite(page) ? Math.max(1, Math.trunc(page)) : 1
    if (next === this.page) {
      return
    }
    this.page = next
    this.notify()
  }

  /**
   * 设置页长（夹取到 `1 ~ PAGE_SIZE_MAX`）。
   *
   * @param size 页长。
   */
  setPageSize(size: number): void {
    const truncated = Math.trunc(size)
    const next = Number.isFinite(truncated) && truncated > 0 ? Math.min(PAGE_SIZE_MAX, truncated) : PAGE_SIZE_DEFAULT
    if (next === this.pageSize) {
      return
    }
    this.pageSize = next
    this.notify()
  }

  /** 回第 1 页（查询 / 重置 / 条件移除后调用）。 */
  resetToFirstPage(): void {
    this.setPage(1)
  }

  /** 列表密度 → 组件根密度档位（`small` → `compact`）。 */
  get densityToken(): 'default' | 'compact' {
    return resolveDensityToken(this.listDensity)
  }

  /**
   * 设置列表密度档位（同时同步组件根密度与根元素属性协议）。
   *
   * @param density 密度。
   */
  setListDensity(density: TableDensity): void {
    if (density === this.listDensity) {
      return
    }
    this.listDensity = density
    this.setProps({ density: resolveDensityToken(density) })
  }

  /**
   * 切换行选中（兼容垫片；新代码用 `selection.toggle`）。
   *
   * @param key 行键。
   */
  toggleSelect(key: string | number): void {
    this.selection.toggle(key)
    this.notify()
  }

  /**
   * 设置当前页行键（配合 `BaseSelection` 的当前页模式剔除越页选中）。
   *
   * @param keys 行键清单。
   */
  setRowKeys(keys: readonly string[]): void {
    this.selection.setPageKeys([...keys])
    this.notify()
  }

  /**
   * 切换行展开。
   *
   * @param key 行键。
   */
  toggleExpand(key: string | number): void {
    const text = String(key)
    if (this.expandedKeys.has(text)) {
      this.expandedKeys.delete(text)
    } else {
      this.expandedKeys.add(text)
    }
    this.notify()
  }

  /**
   * 展开全部（未传键时按当前行数据收集）。
   *
   * @param keys 行键清单。
   */
  expandAll(keys?: readonly string[]): void {
    const target = keys ?? collectTreeKeys(this.rows, this.rowKey, this.childrenKey)
    for (const key of target) {
      this.expandedKeys.add(key)
    }
    this.notify(target.length > 0)
  }

  /** 收起全部。 */
  collapseAll(): void {
    if (this.expandedKeys.size === 0) {
      return
    }
    this.expandedKeys.clear()
    this.notify()
  }

  /**
   * 设置行内编辑态。
   *
   * @param value 是否可编辑。
   */
  setEditable(value: boolean): void {
    if (value === this.editable) {
      return
    }
    this.editable = value
    this.notify()
  }

  /**
   * 广播变更（`changed` 为假时跳过，避免无谓刷新）。
   *
   * @param changed 是否确有变更（缺省为真）。
   */
  private notify(changed = true): void {
    if (changed && !this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
