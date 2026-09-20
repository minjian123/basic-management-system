/**
 * 表格契约（`@bms/core/testing`）。
 *
 * 通用表格（`07_05`）/ 移动端与后续列表件为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 分页夹取、多列排序叠加与参数序列化、密度映射、列归一与末列保护、多选与树形展开。
 */

import { describe, expect, it } from 'vitest'

import type { ColumnSeed, TableColumn, TableDensity, TableSortParams, TableSortSpec } from '../src'

/** 表格契约面（结构化接口）。 */
export interface TableContractTarget {
  /** 行数据。 */
  readonly rows: readonly unknown[]
  /** 总条数。 */
  readonly total: number
  /** 页码。 */
  readonly page: number
  /** 页长。 */
  readonly pageSize: number
  /** 多列排序。 */
  readonly sorts: readonly TableSortSpec[]
  /** 列表密度档位。 */
  readonly listDensity: TableDensity
  /** 组件根密度档位（`small` → `compact`）。 */
  readonly densityToken: 'default' | 'compact'
  /** 选中行键。 */
  readonly selectedKeys: readonly string[]
  /** 可见列键。 */
  readonly columnKeys: readonly string[]
  /** 已展开行键。 */
  readonly expandedKeys: readonly string[]
  /** 设置行数据。 */
  setRows(rows: readonly unknown[], total?: number): void
  /** 设置页码。 */
  setPage(page: number): void
  /** 设置页长。 */
  setPageSize(size: number): void
  /** 回第 1 页。 */
  resetToFirstPage(): void
  /** 切换排序。 */
  toggleSort(column: TableColumn, additive?: boolean): readonly TableSortSpec[]
  /** 排序参数。 */
  sortParams(): TableSortParams
  /** 设置列表密度。 */
  setListDensity(density: TableDensity): void
  /** 设置列显隐。 */
  setVisible(key: string, visible: boolean): void
  /** 与列种子归一。 */
  normalizeColumns(seeds: readonly ColumnSeed[]): void
  /** 切换行选中。 */
  toggleSelect(key: string): void
  /** 切换行展开。 */
  toggleExpand(key: string): void
  /** 展开全部。 */
  expandAll(keys?: readonly string[]): void
  /** 收起全部。 */
  collapseAll(): void
}

/**
 * 表格契约（`07_05` 冻结；真实实现与后续列表件继续跑同一套件）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeTableContract(name: string, create: () => TableContractTarget): void {
  describe(name, () => {
    it('分页夹取与回第 1 页', () => {
      const target = create()
      target.setPage(3)
      expect(target.page).toBe(3)
      target.setPage(-5)
      expect(target.page).toBe(1)

      target.setPageSize(500)
      expect(target.pageSize).toBe(200)
      target.setPageSize(0)
      expect(target.pageSize).toBe(20)

      target.setPage(4)
      target.resetToFirstPage()
      expect(target.page).toBe(1)
    })

    it('多列排序：叠加 ≤ 3 列、方向切换与参数序列化', () => {
      const target = create()
      const a: TableColumn = { key: 'a', title: 'A' }
      const b: TableColumn = { key: 'b', title: 'B' }
      const c: TableColumn = { key: 'c', title: 'C' }
      const d: TableColumn = { key: 'd', title: 'D' }

      expect(target.toggleSort(a)).toEqual([{ field: 'a', order: 'asc' }])
      expect(target.toggleSort(b, true)).toEqual([
        { field: 'a', order: 'asc' },
        { field: 'b', order: 'asc' },
      ])
      expect(target.toggleSort(c, true)).toHaveLength(3)
      expect(target.toggleSort(d, true)).toHaveLength(3)
      expect(target.sortParams()).toEqual({ order_by: 'a,b,c', order: ['asc', 'asc', 'asc'] })

      expect(target.toggleSort(a)).toEqual([{ field: 'a', order: 'desc' }])
      expect(target.toggleSort(a)).toEqual([])
      expect(target.sortParams()).toEqual({})
    })

    it('密度：持久化取值 default|small，根密度映射 compact', () => {
      const target = create()
      target.setListDensity('small')
      expect(target.listDensity).toBe('small')
      expect(target.densityToken).toBe('compact')

      target.setListDensity('default')
      expect(target.listDensity).toBe('default')
      expect(target.densityToken).toBe('default')
    })

    it('列归一：剔除已删列、追加新增列、末列不可隐藏', () => {
      const target = create()
      target.normalizeColumns([{ key: 'a' }, { key: 'b' }])
      expect(target.columnKeys).toEqual(['a', 'b'])

      target.setVisible('b', false)
      expect(target.columnKeys).toEqual(['a'])
      target.setVisible('a', false)
      expect(target.columnKeys).toEqual(['a'])

      target.setVisible('b', true)
      target.normalizeColumns([{ key: 'b' }, { key: 'c' }])
      expect(target.columnKeys).toEqual(['b', 'c'])
    })

    it('多选与树形展开', () => {
      const target = create()
      target.setRows([{ id: 1 }, { id: 2 }], 2)
      expect(target.total).toBe(2)

      target.toggleSelect('1')
      expect(target.selectedKeys).toEqual(['1'])
      target.toggleSelect('1')
      expect(target.selectedKeys).toEqual([])

      target.expandAll()
      expect(target.expandedKeys).toEqual(['1', '2'])
      target.collapseAll()
      expect(target.expandedKeys).toEqual([])
      target.toggleExpand('2')
      expect(target.expandedKeys).toEqual(['2'])
    })
  })
}
