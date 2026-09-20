/** 领域纯函数：表格（列合并 / 渲染优先级 / 可见列 / 排序参数 / 树形展平 / 自动列宽 / 虚拟阈值）。 */

import { describe, expect, it } from 'vitest'

import {
  MAX_SORT_COLUMNS,
  PAGE_SIZE_MAX,
  TABLE_DEFAULT_COLUMN_WIDTH,
  TABLE_MIN_COLUMN_WIDTH,
  VIRTUAL_ROW_THRESHOLD,
  buildSortParams,
  clampColumnWidth,
  collectTreeKeys,
  columnSignature,
  flattenTreeRows,
  isVirtualEnabled,
  measureAutoWidth,
  mergeTableColumns,
  parseSortParams,
  resolveColumnStyle,
  resolveDensityToken,
  resolveRenderKind,
  resolveVisibleColumns,
  rowKeyOf,
  sortFieldOf,
  sortIndexOf,
  tableCellText,
  toggleSort,
} from '../src'

describe('列配置解析', () => {
  it('声明式列与元数据列按字段名合并（元数据默认、声明覆盖）', () => {
    const merged = mergeTableColumns(
      [
        { key: 'name', title: '姓名' },
        { key: 'amount', title: '金额', width: 200 },
      ],
      [
        { key: 'name', title: '用户名', width: 180, visible: false },
        { key: 'created_at', title: '创建时间', width: 160 },
      ],
    )
    expect(merged.map((column) => column.key)).toEqual(['name', 'amount', 'created_at'])
    expect(merged[0]).toMatchObject({ title: '姓名', width: 180, visible: false })
    expect(merged[1]).toMatchObject({ width: 200 })
    expect(merged[2]).toMatchObject({ title: '创建时间', width: 160 })
  })

  it('渲染优先级：字典 → 状态 → 脱敏 → 格式化 → 原值', () => {
    expect(resolveRenderKind({ key: 'a', title: 'A' })).toBe('raw')
    expect(resolveRenderKind({ key: 'a', title: 'A', format: 'amount' })).toBe('format')
    expect(resolveRenderKind({ key: 'a', title: 'A', format: 'amount', mask: true })).toBe('mask')
    expect(resolveRenderKind({ key: 'a', title: 'A', status: true })).toBe('status')
    expect(resolveRenderKind({ key: 'a', title: 'A', status: true, dictType: 'sys_status' })).toBe('dict')
  })

  it('可见列按偏好过滤与排序，偏好缺失列保留在末尾', () => {
    const columns = [
      { key: 'a', title: 'A' },
      { key: 'b', title: 'B' },
      { key: 'c', title: 'C' },
    ]
    expect(resolveVisibleColumns(columns).map((column) => column.key)).toEqual(['a', 'b', 'c'])
    expect(
      resolveVisibleColumns(columns, [
        { key: 'b', visible: true, order: 0 },
        { key: 'a', visible: true, order: 1 },
        { key: 'c', visible: false, order: 2 },
      ]).map((column) => column.key),
    ).toEqual(['b', 'a'])
    expect(
      resolveVisibleColumns(columns, [{ key: 'a', visible: false, order: 0 }]).map((column) => column.key),
    ).toEqual(['b', 'c'])
  })

  it('列宽夹取与样式解析', () => {
    expect(clampColumnWidth(10)).toBe(TABLE_MIN_COLUMN_WIDTH)
    expect(clampColumnWidth(Number.NaN)).toBe(TABLE_DEFAULT_COLUMN_WIDTH)
    expect(resolveColumnStyle({ key: 'a', title: 'A', width: 200 })).toEqual({ width: '200px', minWidth: '200px' })
    expect(resolveColumnStyle({ key: 'a', title: 'A' })).toEqual({ minWidth: `${TABLE_DEFAULT_COLUMN_WIDTH}px` })
  })

  it('排序字段名与优先级序号', () => {
    expect(sortFieldOf({ key: 'a', title: 'A' })).toBe('a')
    expect(sortFieldOf({ key: 'a', title: 'A', sortField: 'created_at' })).toBe('created_at')
    expect(sortIndexOf([{ field: 'a', order: 'asc' }], 'a')).toBe(0)
    expect(sortIndexOf([{ field: 'a', order: 'asc' }], 'b')).toBe(-1)
  })

  it('列签名稳定', () => {
    expect(columnSignature([{ key: 'a', title: 'A' }])).toBe(columnSignature([{ key: 'a', title: 'A' }]))
    expect(columnSignature([{ key: 'a', title: 'A' }])).not.toBe(columnSignature([{ key: 'b', title: 'B' }]))
  })
})

describe('多列排序', () => {
  it('非叠加单列切换：升 → 降 → 取消', () => {
    const column = { key: 'a', title: 'A' }
    let sorts = toggleSort([], column)
    expect(sorts).toEqual([{ field: 'a', order: 'asc' }])
    sorts = toggleSort(sorts, column)
    expect(sorts).toEqual([{ field: 'a', order: 'desc' }])
    sorts = toggleSort(sorts, column)
    expect(sorts).toEqual([])
  })

  it('叠加 ≤ 3 列并保序', () => {
    let sorts = toggleSort([], { key: 'a', title: 'A' }, true)
    sorts = toggleSort(sorts, { key: 'b', title: 'B' }, true)
    sorts = toggleSort(sorts, { key: 'c', title: 'C' }, true)
    expect(sorts).toHaveLength(MAX_SORT_COLUMNS)
    sorts = toggleSort(sorts, { key: 'd', title: 'D' }, true)
    expect(sorts.map((item) => item.field)).toEqual(['a', 'b', 'c'])

    sorts = toggleSort(sorts, { key: 'b', title: 'B' }, true)
    expect(sorts[1]).toEqual({ field: 'b', order: 'desc' })
  })
})

describe('排序参数', () => {
  it('构造与解析（方向缺省 desc）', () => {
    expect(buildSortParams([])).toEqual({})
    expect(
      buildSortParams([
        { field: 'a', order: 'asc' },
        { field: 'b', order: 'desc' },
      ]),
    ).toEqual({
      order_by: 'a,b',
      order: ['asc', 'desc'],
    })
    expect(parseSortParams('a,b, a', ['asc'])).toEqual([
      { field: 'a', order: 'asc' },
      { field: 'b', order: 'desc' },
    ])
    expect(parseSortParams(undefined)).toEqual([])
  })
})

describe('树形展平', () => {
  const rows = [{ id: '1', children: [{ id: '1-1' }, { id: '1-2', children: [{ id: '1-2-1' }] }] }, { id: '2' }]

  it('仅展开节点下沉', () => {
    const collapsed = flattenTreeRows(rows, { rowKey: 'id', childrenKey: 'children', expandedKeys: new Set() })
    expect(collapsed.map((row) => row.key)).toEqual(['1', '2'])
    expect(collapsed[0]).toMatchObject({ level: 0, hasChildren: true, expanded: false })
    expect(collapsed[1]).toMatchObject({ level: 0, hasChildren: false })

    const expanded = flattenTreeRows(rows, {
      rowKey: 'id',
      childrenKey: 'children',
      expandedKeys: new Set(['1', '1-2']),
    })
    expect(expanded.map((row) => row.key)).toEqual(['1', '1-1', '1-2', '1-2-1', '2'])
    expect(expanded[2]).toMatchObject({ level: 1, hasChildren: true })
    expect(expanded[3]).toMatchObject({ level: 2 })
  })

  it('数字键兼容与全量键收集', () => {
    const numeric = flattenTreeRows([{ id: 1, children: [{ id: 2 }] }], {
      rowKey: 'id',
      childrenKey: 'children',
      expandedKeys: new Set([1]),
    })
    expect(numeric.map((row) => row.key)).toEqual(['1', '2'])
    expect(collectTreeKeys(rows, 'id')).toEqual(['1', '1-1', '1-2', '1-2-1', '2'])
  })
})

describe('行键与单元格文本', () => {
  it('空值统一占位', () => {
    expect(rowKeyOf({ id: 5 }, 'id')).toBe('5')
    expect(rowKeyOf(null, 'id')).toBe('')
    expect(tableCellText({ a: null }, 'a')).toBe('—')
    expect(tableCellText({ a: 0 }, 'a')).toBe('0')
  })
})

describe('密度 / 虚拟 / 自动列宽', () => {
  it('密度映射与虚拟阈值', () => {
    expect(resolveDensityToken('small')).toBe('compact')
    expect(resolveDensityToken('default')).toBe('default')
    expect(isVirtualEnabled(true, VIRTUAL_ROW_THRESHOLD)).toBe(true)
    expect(isVirtualEnabled(true, 10)).toBe(false)
    expect(isVirtualEnabled(false, 1000)).toBe(false)
  })

  it('自动列宽按列头与内容估算', () => {
    const rows = [{ name: '甲' }, { name: '很长很长的名称文本内容' }]
    const width = measureAutoWidth('名称', rows, 'name')
    expect(width).toBeGreaterThan(TABLE_MIN_COLUMN_WIDTH)
    expect(measureAutoWidth('名', [], 'name')).toBeGreaterThanOrEqual(TABLE_MIN_COLUMN_WIDTH)
    expect(PAGE_SIZE_MAX).toBe(200)
  })
})
