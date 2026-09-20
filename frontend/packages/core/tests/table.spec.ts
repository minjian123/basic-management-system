/** 表格组件基类（`BaseTable`：分页 / 多列排序 / 组合多选与列配置 / 树形 / 行内编辑）+ 表格契约套件。 */

import { describeTableContract, type TableContractTarget } from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

import { BaseColumnConfig, BaseDataState, BaseSelection, BaseTable, type TableColumn } from '../src'

/** 具体表格件（可实例化）。 */
class DemoTable extends BaseTable {}

/** 契约目标：表格基类实例。 */
function makeTarget(): TableContractTarget {
  const table = new DemoTable()
  return {
    get rows() {
      return table.rows
    },
    get total() {
      return table.total
    },
    get page() {
      return table.page
    },
    get pageSize() {
      return table.pageSize
    },
    get sorts() {
      return table.sorts
    },
    get listDensity() {
      return table.listDensity
    },
    get densityToken() {
      return table.densityToken
    },
    get selectedKeys() {
      return table.selectedKeys
    },
    get columnKeys() {
      return table.columnConfig.visibleOrder
    },
    get expandedKeys() {
      return [...table.expandedKeys].map((key) => String(key))
    },
    setRows: (rows, total) => table.setRows(rows, total),
    setPage: (page) => table.setPage(page),
    setPageSize: (size) => table.setPageSize(size),
    resetToFirstPage: () => table.resetToFirstPage(),
    toggleSort: (column, additive) => table.toggleSort(column, additive),
    sortParams: () => table.sortParams(),
    setListDensity: (density) => table.setListDensity(density),
    setVisible: (key, visible) => table.columnConfig.setVisible(key, visible),
    normalizeColumns: (seeds) => table.columnConfig.normalizeWith(seeds),
    toggleSelect: (key) => table.toggleSelect(key),
    toggleExpand: (key) => table.toggleExpand(key),
    expandAll: (keys) => table.expandAll(keys),
    collapseAll: () => table.collapseAll(),
  }
}

describeTableContract('表格契约（BaseTable）', makeTarget)

describe('BaseTable 继承与组合', () => {
  it('继承数据状态能力基类，组合多选与列配置（非继承）', () => {
    const table = new DemoTable()
    expect(table).toBeInstanceOf(BaseDataState)
    expect(table.identifier).toBe('table')
    expect(table.key).toBe('table')
    expect(table.depends).toEqual(['data-state', 'selection', 'column-config'])
    expect(table.selection).toBeInstanceOf(BaseSelection)
    expect(table.columnConfig).toBeInstanceOf(BaseColumnConfig)
  })
})

describe('BaseTable 数据 / 分页 / 选择', () => {
  it('设置行数据同步总条数与当前页行键', () => {
    const table = new DemoTable()
    table.setRows([{ id: 1 }, { id: 2 }])
    expect(table.total).toBe(2)
    expect(table.selection.pageKeys).toEqual(['1', '2'])
  })

  it('页长缺省与夹取', () => {
    const table = new DemoTable()
    expect(table.pageSize).toBe(20)
    table.setPageSize(0)
    expect(table.pageSize).toBe(20)
    table.setPageSize(50)
    expect(table.pageSize).toBe(50)
    table.setPageSize(1000)
    expect(table.pageSize).toBe(200)
  })

  it('多选与兼容垫片一致', () => {
    const table = new DemoTable()
    table.setRows([{ id: 'a' }], 1)
    table.toggleSelect('a')
    expect(table.selectedKeys).toEqual(['a'])
    expect([...table.selected]).toEqual(['a'])
    expect(table.selection.count).toBe(1)
    table.selection.clear()
    expect(table.selectedKeys).toEqual([])
  })

  it('跨页全选需跨页模式', () => {
    const table = new DemoTable()
    table.setRows([{ id: 'a' }], 30)
    table.selection.selectAllAcrossPages()
    expect(table.selection.allAcrossPages).toBe(false)
    table.selection.setMode('cross-page')
    table.selection.selectAllAcrossPages()
    expect(table.selection.summary).toEqual({ count: 30, allAcrossPages: true, total: 30, mode: 'cross-page' })
  })

  it('列宽与顺序经列配置组件基类', () => {
    const table = new DemoTable()
    table.columnConfig.normalizeWith([{ key: 'a' }, { key: 'b' }, { key: 'c' }])
    table.columnConfig.moveColumn('c', -2)
    expect(table.columnConfig.visibleOrder).toEqual(['c', 'a', 'b'])
    table.columnConfig.setWidth('a', 10)
    expect(table.columnConfig.columns.find((column) => column.key === 'a')?.width).toBe(60)
    table.columnConfig.resetColumns([{ key: 'a' }, { key: 'b' }])
    expect(table.columnConfig.visibleOrder).toEqual(['a', 'b'])
    expect(table.columnConfig.has('c')).toBe(false)
  })
})

describe('BaseTable 树形与行内编辑', () => {
  const columns: TableColumn = { key: 'name', title: '名称', sortable: true }

  it('展开 / 收起 / 展开全部（按行数据收集键）', () => {
    const table = new DemoTable()
    table.tree = true
    table.setRows([{ id: '1', children: [{ id: '1-1' }] }, { id: '2' }])
    table.toggleExpand('1')
    expect([...table.expandedKeys]).toEqual(['1'])
    table.toggleExpand('1')
    expect([...table.expandedKeys]).toEqual([])
    table.expandAll()
    expect([...table.expandedKeys]).toEqual(['1', '1-1', '2'])
    table.collapseAll()
    expect([...table.expandedKeys]).toEqual([])
    table.expandAll(['9'])
    expect([...table.expandedKeys]).toEqual(['9'])
  })

  it('单列排序兼容接口与多列排序同步', () => {
    const table = new DemoTable()
    table.sortBy('created_at', 'desc')
    expect(table.sort).toEqual({ field: 'created_at', order: 'desc' })
    expect(table.sortParams()).toEqual({ order_by: 'created_at', order: ['desc'] })
    table.toggleSort(columns)
    expect(table.sort).toEqual({ field: 'name', order: 'asc' })
    table.clearSort()
    expect(table.sorts).toEqual([])
    expect(table.sort).toBeUndefined()
  })

  it('密度映射与行内编辑态', () => {
    const table = new DemoTable()
    table.setListDensity('small')
    expect(table.listDensity).toBe('small')
    expect(table.densityToken).toBe('compact')
    expect(table.density).toBe('compact')
    table.setEditable(true)
    expect(table.editable).toBe(true)
    table.setEditable(true)
    expect(table.editable).toBe(true)
  })
})
