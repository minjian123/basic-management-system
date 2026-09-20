/**
 * 领域纯函数：表格（列合并与渲染优先级 / 可见列 / 多列排序参数 / 树形展平 / 自动列宽 / 虚拟阈值）。
 *
 * 不触 DOM、不请求、不依赖渲染框架与第三方库；同输入同输出。
 */

import { EMPTY_PLACEHOLDER } from './format'

/** 列对齐。 */
export type TableColumnAlign = 'left' | 'center' | 'right'

/** 列固定位置。 */
export type TableColumnFixed = 'left' | 'right'

/** 列值格式化口径（复用 `domain/format.ts`）。 */
export type TableColumnFormat = 'number' | 'amount' | 'percent' | 'date' | 'datetime' | 'fileSize' | 'boolean'

/** 表格密度档位（与后端列表偏好契约同源）。 */
export type TableDensity = 'default' | 'small'

/** 列渲染类型。 */
export type TableRenderKind = 'slot' | 'dict' | 'status' | 'mask' | 'format' | 'raw'

/** 列渲染优先级（自上而下命中即用）。 */
export const TABLE_RENDER_PRIORITY: readonly TableRenderKind[] = ['slot', 'dict', 'status', 'mask', 'format', 'raw']

/** 表格列声明（声明式列配置）。 */
export interface TableColumn {
  /** 列键（与后端字段同名）。 */
  key: string
  /** 列头文案。 */
  title: string
  /** 固定列宽（px）。 */
  width?: number
  /** 自适应最小宽度（px）。 */
  minWidth?: number
  /** 对齐。 */
  align?: TableColumnAlign
  /** 固定位置。 */
  fixed?: TableColumnFixed
  /** 是否参与排序。 */
  sortable?: boolean
  /** 后端排序字段名（缺省取列键）。 */
  sortField?: string
  /** 溢出省略 + 悬浮全文。 */
  ellipsis?: boolean
  /** 格式化口径。 */
  format?: TableColumnFormat
  /** 字典类型（字典列批量翻译）。 */
  dictType?: string
  /** 是否状态列（由状态标签渲染）。 */
  status?: boolean
  /** 是否脱敏列。 */
  mask?: boolean
  /** 默认是否可见（缺省可见）。 */
  visible?: boolean
  /** 行内编辑模式下是否可编辑。 */
  editable?: boolean
  /** 是否仅本地排序（数据已全量在前端时）。 */
  localSort?: boolean
}

/** 表单元数据生成的列（明细区列配置 → 表列映射）。 */
export interface TableColumnMeta {
  /** 字段名。 */
  key: string
  /** 列头文案。 */
  title: string
  /** 固定列宽（px）。 */
  width?: number
  /** 固定位置。 */
  fixed?: TableColumnFixed
  /** 默认是否可见。 */
  visible?: boolean
}

/** 列状态（偏好归一形态；与列配置组件基类的 `ColumnState` 结构一致）。 */
export interface TableColumnState {
  /** 列键。 */
  key: string
  /** 是否可见。 */
  visible: boolean
  /** 顺序（自 0 起）。 */
  order: number
  /** 宽度。 */
  width?: number
}

/** 排序规格。 */
export interface TableSortSpec {
  /** 排序字段。 */
  field: string
  /** 方向。 */
  order: 'asc' | 'desc'
}

/** 树形展平行。 */
export interface TableTreeRow {
  /** 行数据。 */
  row: unknown
  /** 行键。 */
  key: string
  /** 层级（自 0 起）。 */
  level: number
  /** 是否有子节点。 */
  hasChildren: boolean
  /** 是否展开。 */
  expanded: boolean
}

/** 树形展平选项。 */
export interface TableTreeOptions {
  /** 行主键字段。 */
  rowKey: string
  /** 子节点字段。 */
  childrenKey: string
  /** 已展开键集合（字符串口径）。 */
  expandedKeys: ReadonlySet<string | number>
}

/** 排序参数（与后端排序契约同源）。 */
export interface TableSortParams {
  /** 排序字段（逗号分隔多值）。 */
  order_by?: string
  /** 方向数组（与字段位置一一对应）。 */
  order?: string[]
}

/** 页长候选。 */
export const PAGE_SIZE_OPTIONS: readonly number[] = [10, 20, 50, 100]

/** 缺省页长。 */
export const PAGE_SIZE_DEFAULT = 20

/** 页长上限。 */
export const PAGE_SIZE_MAX = 200

/** 明细区缺省页长（≤ 10 行不分页）。 */
export const DETAIL_PAGE_SIZE_DEFAULT = 10

/** 多列排序上限。 */
export const MAX_SORT_COLUMNS = 3

/** 虚拟滚动阈值（显式开启时进入虚拟模式的建议行数下限）。 */
export const VIRTUAL_ROW_THRESHOLD = 200

/** 列宽下限。 */
export const TABLE_MIN_COLUMN_WIDTH = 60

/** 缺省列宽（自适应基准）。 */
export const TABLE_DEFAULT_COLUMN_WIDTH = 160

/** 自动列宽采样行数。 */
export const AUTO_WIDTH_SAMPLE_ROWS = 20

/** 自动列宽每个字符的估算宽度（px）。 */
export const TABLE_CHAR_WIDTH = 8

/** 自动列宽附加留白（px）。 */
export const TABLE_AUTO_WIDTH_PADDING = 24

/** 布尔列真值文案。 */
export const TABLE_BOOLEAN_TRUE_TEXT = '是'

/** 布尔列假值文案。 */
export const TABLE_BOOLEAN_FALSE_TEXT = '否'

/** 子节点读取。 */
function childrenOf(row: unknown, childrenKey: string): readonly unknown[] {
  if (row === null || typeof row !== 'object') {
    return []
  }
  const value = (row as Record<string, unknown>)[childrenKey]
  return Array.isArray(value) ? (value as readonly unknown[]) : []
}

/** 单元格文本（空值回落占位）。 */
function cellText(row: unknown, key: string): string {
  if (row === null || typeof row !== 'object') {
    return EMPTY_PLACEHOLDER
  }
  const value = (row as Record<string, unknown>)[key]
  if (value === null || value === undefined || value === '') {
    return EMPTY_PLACEHOLDER
  }
  return String(value)
}

/** 文本视觉宽度（中日韩字符按 2 计）。 */
function textUnits(text: string): number {
  let units = 0
  for (const char of text) {
    units += /[\u2E80-\uFFFD]/.test(char) ? 2 : 1
  }
  return units
}

/** 是否已展开（兼容字符串 / 数字两种键形态）。 */
function isExpanded(keys: ReadonlySet<string | number>, key: string): boolean {
  if (keys.has(key)) {
    return true
  }
  const numeric = Number(key)
  return !Number.isNaN(numeric) && keys.has(numeric)
}

/**
 * 合并声明式列与元数据列（元数据提供默认，声明可覆盖）。
 *
 * @param declared 声明式列。
 * @param meta 元数据列（可选）。
 * @returns 合并后的列（顺序按声明列，缺项追加元数据列）。
 */
export function mergeTableColumns(
  declared: readonly TableColumn[],
  meta: readonly TableColumnMeta[] = [],
): TableColumn[] {
  const metaByKey = new Map(meta.map((item) => [item.key, item]))
  const merged: TableColumn[] = declared.map((column) => {
    const fallback = metaByKey.get(column.key)
    if (fallback === undefined) {
      return { ...column }
    }
    return {
      ...column,
      title: column.title === '' ? fallback.title : column.title,
      width: column.width ?? fallback.width,
      fixed: column.fixed ?? fallback.fixed,
      visible: column.visible ?? fallback.visible,
    }
  })
  const declaredKeys = new Set(declared.map((column) => column.key))
  for (const item of meta) {
    if (!declaredKeys.has(item.key)) {
      merged.push({ key: item.key, title: item.title, width: item.width, fixed: item.fixed, visible: item.visible })
    }
  }
  return merged
}

/**
 * 解析列的渲染类型（优先级：插槽 → 字典 → 状态 → 脱敏 → 格式化 → 原值）。
 *
 * @param column 列声明。
 * @returns 渲染类型。
 */
export function resolveRenderKind(column: TableColumn): TableRenderKind {
  if (column.dictType !== undefined && column.dictType !== '') {
    return 'dict'
  }
  if (column.status === true) {
    return 'status'
  }
  if (column.mask === true) {
    return 'mask'
  }
  if (column.format !== undefined) {
    return 'format'
  }
  return 'raw'
}

/**
 * 计算可见列（按偏好状态过滤并按顺序排序）。
 *
 * @param columns 列声明。
 * @param states 列状态（可选；缺省按列声明顺序全量可见）。
 * @returns 可见列。
 */
export function resolveVisibleColumns(
  columns: readonly TableColumn[],
  states?: readonly TableColumnState[],
): TableColumn[] {
  if (states === undefined || states.length === 0) {
    return columns.filter((column) => column.visible !== false)
  }
  const stateByKey = new Map(states.map((state) => [state.key, state]))
  const known = columns.filter((column) => stateByKey.has(column.key))
  const unknown = columns.filter((column) => !stateByKey.has(column.key))
  const visible = known
    .filter((column) => stateByKey.get(column.key)?.visible === true)
    .sort((left, right) => (stateByKey.get(left.key)?.order ?? 0) - (stateByKey.get(right.key)?.order ?? 0))
  return [...visible, ...unknown.filter((column) => column.visible !== false)]
}

/**
 * 解析列的宽高样式（显式宽度优先，否则给出自适应最小宽度）。
 *
 * @param column 列声明。
 * @returns 宽高样式片段。
 */
export function resolveColumnStyle(column: TableColumn): { width?: string; minWidth: string } {
  const minWidth = clampColumnWidth(column.minWidth ?? column.width ?? TABLE_DEFAULT_COLUMN_WIDTH)
  if (column.width !== undefined) {
    return { width: `${clampColumnWidth(column.width)}px`, minWidth: `${minWidth}px` }
  }
  return { minWidth: `${minWidth}px` }
}

/**
 * 列的后端排序字段名。
 *
 * @param column 列声明。
 * @returns 排序字段名。
 */
export function sortFieldOf(column: TableColumn): string {
  return column.sortField ?? column.key
}

/**
 * 切换排序（非叠加时单列，叠加时按追加顺序，最多 `MAX_SORT_COLUMNS` 列）。
 *
 * @param sorts 当前排序。
 * @param column 目标列。
 * @param additive 是否叠加（Shift 点击）。
 * @returns 新排序列表。
 */
export function toggleSort(sorts: readonly TableSortSpec[], column: TableColumn, additive = false): TableSortSpec[] {
  const field = sortFieldOf(column)
  const index = sorts.findIndex((item) => item.field === field)
  const current = index >= 0 ? sorts[index] : undefined
  const nextOrder: 'asc' | 'desc' = current?.order === 'asc' ? 'desc' : 'asc'
  if (!additive) {
    if (current !== undefined && current.order === 'desc') {
      return []
    }
    return [{ field, order: nextOrder }]
  }
  if (index >= 0) {
    const next = sorts.map((item) => ({ ...item }))
    next[index] = { field, order: nextOrder }
    return next
  }
  if (sorts.length >= MAX_SORT_COLUMNS) {
    return [...sorts]
  }
  return [...sorts, { field, order: 'asc' }]
}

/**
 * 构造排序参数（`order_by` 逗号分隔 + `order` 方向数组）。
 *
 * @param sorts 排序列表。
 * @returns 排序参数（空集合返回空对象）。
 */
export function buildSortParams(sorts: readonly TableSortSpec[]): TableSortParams {
  if (sorts.length === 0) {
    return {}
  }
  return { order_by: sorts.map((item) => item.field).join(','), order: sorts.map((item) => item.order) }
}

/**
 * 解析排序参数（方向缺位回退 `desc`，同字段去重保留首次）。
 *
 * @param orderBy 排序字段（逗号分隔多值）。
 * @param order 方向数组（与字段位置一一对应）。
 * @returns 排序列表。
 */
export function parseSortParams(orderBy: string | undefined, order: readonly string[] = []): TableSortSpec[] {
  const names = (orderBy ?? '')
    .split(',')
    .map((name) => name.trim())
    .filter((name) => name !== '')
  const result: TableSortSpec[] = []
  const seen = new Set<string>()
  for (const [index, name] of names.entries()) {
    if (seen.has(name)) {
      continue
    }
    seen.add(name)
    const direction = (order[index] ?? '').toLowerCase()
    result.push({ field: name, order: direction === 'asc' ? 'asc' : 'desc' })
  }
  return result
}

/**
 * 排序列表中某字段的优先级序号（未命中返回 `-1`）。
 *
 * @param sorts 排序列表。
 * @param field 排序字段。
 * @returns 序号（自 0 起）。
 */
export function sortIndexOf(sorts: readonly TableSortSpec[], field: string): number {
  return sorts.findIndex((item) => item.field === field)
}

/**
 * 行键归一（统一字符串）。
 *
 * @param row 行数据。
 * @param rowKey 行主键字段。
 * @returns 行键。
 */
export function rowKeyOf(row: unknown, rowKey: string): string {
  if (row === null || typeof row !== 'object') {
    return ''
  }
  const value = (row as Record<string, unknown>)[rowKey]
  return value === null || value === undefined ? '' : String(value)
}

/**
 * 展平树形行（仅展开节点下沉）。
 *
 * @param rows 行数据。
 * @param options 树形选项。
 * @returns 展平后的行（带层级与展开态）。
 */
export function flattenTreeRows(rows: readonly unknown[], options: TableTreeOptions): TableTreeRow[] {
  const result: TableTreeRow[] = []
  const walk = (list: readonly unknown[], level: number): void => {
    for (const row of list) {
      const key = rowKeyOf(row, options.rowKey)
      const children = childrenOf(row, options.childrenKey)
      const expanded = children.length > 0 && isExpanded(options.expandedKeys, key)
      result.push({ row, key, level, hasChildren: children.length > 0, expanded })
      if (expanded) {
        walk(children, level + 1)
      }
    }
  }
  walk(rows, 0)
  return result
}

/**
 * 收集全量行键（含未展开子树）。
 *
 * @param rows 行数据。
 * @param rowKey 行主键字段。
 * @param childrenKey 子节点字段（缺省 `children`）。
 * @returns 行键清单。
 */
export function collectTreeKeys(rows: readonly unknown[], rowKey: string, childrenKey = 'children'): string[] {
  const result: string[] = []
  const walk = (list: readonly unknown[]): void => {
    for (const row of list) {
      result.push(rowKeyOf(row, rowKey))
      walk(childrenOf(row, childrenKey))
    }
  }
  walk(rows)
  return result
}

/**
 * 密度档位 → 根元素 `data-density` 取值。
 *
 * @param density 密度档位。
 * @returns `data-density` 取值。
 */
export function resolveDensityToken(density: TableDensity): 'default' | 'compact' {
  return density === 'small' ? 'compact' : 'default'
}

/**
 * 是否启用虚拟模式（显式开启且行数达阈值）。
 *
 * @param virtual 是否显式开启。
 * @param rowCount 行数。
 * @returns 是否启用。
 */
export function isVirtualEnabled(virtual: boolean, rowCount: number): boolean {
  return virtual && rowCount >= VIRTUAL_ROW_THRESHOLD
}

/**
 * 列宽夹取（下限 `TABLE_MIN_COLUMN_WIDTH`）。
 *
 * @param width 原始宽度。
 * @returns 夹取后的宽度。
 */
export function clampColumnWidth(width: number): number {
  if (!Number.isFinite(width)) {
    return TABLE_DEFAULT_COLUMN_WIDTH
  }
  return Math.max(TABLE_MIN_COLUMN_WIDTH, Math.round(width))
}

/**
 * 自动列宽测算（按列头与当前页前若干行内容估算，纯函数无 DOM 测量）。
 *
 * @param title 列头文案。
 * @param rows 行数据。
 * @param key 列键。
 * @param sample 采样行数（缺省 `AUTO_WIDTH_SAMPLE_ROWS`）。
 * @returns 测算宽度（已夹取）。
 */
export function measureAutoWidth(
  title: string,
  rows: readonly unknown[],
  key: string,
  sample = AUTO_WIDTH_SAMPLE_ROWS,
): number {
  let units = textUnits(title)
  for (const row of rows.slice(0, sample)) {
    units = Math.max(units, textUnits(cellText(row, key)))
  }
  return clampColumnWidth(units * TABLE_CHAR_WIDTH + TABLE_AUTO_WIDTH_PADDING)
}

/**
 * 列签名（用于判断列声明是否变化）。
 *
 * @param columns 列声明。
 * @returns 稳定签名。
 */
export function columnSignature(columns: readonly TableColumn[]): string {
  return columns.map((column) => `${column.key}:${column.width ?? ''}:${String(column.visible ?? true)}`).join('|')
}

/**
 * 表格单元格文本（空值统一占位）。
 *
 * @param row 行数据。
 * @param key 列键。
 * @returns 文本。
 */
export function tableCellText(row: unknown, key: string): string {
  return cellText(row, key)
}
