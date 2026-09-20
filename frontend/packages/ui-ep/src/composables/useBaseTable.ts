/** 表格投影：把核心表格组件基类 `BaseTable` 投影为组合式（分页 / 多列排序 / 列配置 / 多选 / 树形 / 密度 / 列表偏好）。 */

import {
  BaseTable,
  buildListPrefKey,
  fromColumnPreferences,
  isListPreferenceOversized,
  mergeTableColumns,
  normalizeListPreference,
  pruneListPreference,
  toColumnPreferences,
  trimListPreference,
  withQuery,
  withoutQuery,
  type ColumnSeed,
  type FilterCondition,
  type FilterField,
  type ListPreference,
  type PersistedRemoteSaver,
  type SelectionSummary,
  type SortSpec,
  type TableColumn,
  type TableColumnMeta,
  type TableDensity,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

import { useBasePersistedState } from './useBasePersistedState'
import { useDisplayPlaceholder } from './useDisplayPlaceholder'

/** 具体表格件（可实例化）。 */
class Table extends BaseTable {}

/** 列声明 → 列种子。 */
function toSeeds(columns: readonly TableColumn[]): ColumnSeed[] {
  return columns.map((column) => ({ key: column.key, width: column.width, visible: column.visible }))
}

/** 选项。 */
export interface UseBaseTableOptions {
  /** 数据通路是否就绪（缺省 `false`，占位零请求）。 */
  ready?: boolean
  /** 列表偏好键标识（给定则启用 `list.{formKey}` 读写）。 */
  formKey?: string
  /** 行主键字段。 */
  rowKey?: string
  /** 页长。 */
  pageSize?: number
  /** 列表密度档位。 */
  listDensity?: TableDensity
  /** 是否树形模式。 */
  tree?: boolean
  /** 子节点字段。 */
  childrenKey?: string
  /** 是否行内编辑模式。 */
  editable?: boolean
  /** 列声明。 */
  columns?: TableColumn[]
  /** 表单元数据列（为声明列提供默认）。 */
  columnMeta?: TableColumnMeta[]
  /** 查询类字段（失效剔除用）。 */
  fields?: FilterField[]
  /** 远端保存注入点（未注入即仅本地）。 */
  remoteSaver?: PersistedRemoteSaver
}

/** `useBaseTable` 返回面。 */
export interface UseBaseTableResult {
  /** 表格基类实例。 */
  table: BaseTable
  /** 是否就绪。 */
  ready: Ref<boolean>
  /** 是否降级（占位）。 */
  degraded: Ref<boolean>
  /** 已发起加载次数（占位态恒 0）。 */
  requestCount: Ref<number>
  /** 行数据。 */
  rows: Ref<unknown[]>
  /** 总条数。 */
  total: Ref<number>
  /** 页码。 */
  page: Ref<number>
  /** 页长。 */
  pageSize: Ref<number>
  /** 多列排序。 */
  sorts: Ref<SortSpec[]>
  /** 列表密度。 */
  listDensity: Ref<TableDensity>
  /** 是否行内编辑。 */
  editable: Ref<boolean>
  /** 列声明（与元数据合并后）。 */
  columns: Ref<TableColumn[]>
  /** 可见列。 */
  visibleColumns: ComputedRef<TableColumn[]>
  /** 选中行键。 */
  selectedKeys: Ref<string[]>
  /** 选中摘要。 */
  summary: Ref<SelectionSummary>
  /** 已展开行键。 */
  expandedKeys: Ref<string[]>
  /** 列偏好。 */
  columnPreferences: Ref<ListPreference['columns']>
  /** 整份列表偏好。 */
  preference: ComputedRef<ListPreference>
  /** 条件偏好。 */
  queryConditions: ComputedRef<FilterCondition[]>
  /** 条件偏好中的关键字。 */
  keyword: ComputedRef<string>
  /** 偏好是否超体积上限。 */
  oversized: ComputedRef<boolean>
  /** 变更序号（实例态非响应式，读它以触发重算）。 */
  revision: Ref<number>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 标记一次加载（仅就绪后计数）。 */
  markLoaded: () => void
  /** 设置行数据。 */
  setRows: (rows: readonly unknown[], total?: number) => void
  /** 设置页码。 */
  setPage: (page: number) => void
  /** 设置页长。 */
  setPageSize: (size: number) => void
  /** 回第 1 页。 */
  resetToFirstPage: () => void
  /** 切换排序。 */
  toggleSort: (column: TableColumn, additive?: boolean) => SortSpec[]
  /** 清空排序。 */
  clearSort: () => void
  /** 设置列表密度。 */
  setListDensity: (density: TableDensity) => void
  /** 设置列显隐。 */
  setVisible: (key: string, visible: boolean) => void
  /** 移动列。 */
  moveColumn: (key: string, offset: number) => void
  /** 设置列宽。 */
  setWidth: (key: string, width: number) => void
  /** 恢复默认列配置。 */
  resetColumns: () => void
  /** 与列声明归一。 */
  normalizeColumns: () => void
  /** 设置列声明（不写偏好；列声明变化时调用）。 */
  setColumns: (next: readonly TableColumn[]) => void
  /** 整体回写排序（受控时调用）。 */
  setSorts: (next: readonly SortSpec[]) => void
  /** 切换行选中。 */
  toggleSelect: (Key: string) => void
  /** 设置当前页行键。 */
  setRowKeys: (keys: readonly string[]) => void
  /** 跨页全选。 */
  selectAllAcrossPages: () => void
  /** 清空选中。 */
  clearSelection: () => void
  /** 切换行展开。 */
  toggleExpand: (key: string) => void
  /** 展开全部。 */
  expandAll: () => void
  /** 收起全部。 */
  collapseAll: () => void
  /** 设置行内编辑态。 */
  setEditable: (value: boolean) => void
  /** 写入条件偏好（列表页取数后调用）。 */
  setQueryConditions: (conditions: readonly FilterCondition[], keyword?: string) => void
  /** 清除条件偏好（「重置」语义）。 */
  clearQuery: () => void
  /** 按字段与列声明剔除失效偏好项（返回剔除的条件数）。 */
  prunePreference: () => number
  /** 以偏好整份回填表状态。 */
  applyPreference: (value: unknown) => void
}

/**
 * 使用表格投影。
 *
 * @param options 选项。
 * @returns 表格基类实例与响应式面。
 */
export function useBaseTable(options: UseBaseTableOptions = {}): UseBaseTableResult {
  const placeholder = useDisplayPlaceholder({ ready: options.ready })
  const table = new Table()
  const columns = ref<TableColumn[]>(mergeTableColumns(options.columns ?? [], options.columnMeta ?? []))

  if (options.rowKey !== undefined) {
    table.rowKey = options.rowKey
  }
  if (options.pageSize !== undefined) {
    table.setPageSize(options.pageSize)
  }
  if (options.listDensity !== undefined) {
    table.setListDensity(options.listDensity)
  }
  if (options.tree !== undefined) {
    table.tree = options.tree
  }
  if (options.childrenKey !== undefined) {
    table.childrenKey = options.childrenKey
  }
  if (options.editable !== undefined) {
    table.editable = options.editable
  }
  table.columnConfig.normalizeWith(toSeeds(columns.value))

  const preferenceState = useBasePersistedState({
    stateKey: options.formKey === undefined ? '' : buildListPrefKey(options.formKey),
    remoteSaver: options.remoteSaver,
  })

  /** 当前偏好（整份）。 */
  const preference = computed<ListPreference>(() => normalizeListPreference(preferenceState.local.value))

  /** 由表状态与既有条件子键组装整份偏好。 */
  const composePreference = (): ListPreference => ({
    columns: toColumnPreferences(table.columnConfig.columns),
    page_size: table.pageSize,
    density: table.listDensity,
    query: preference.value.query,
  })

  /** 写回偏好（裁剪后落本地并防抖保存）。 */
  const commit = (next: ListPreference): void => {
    preferenceState.setLocal(trimListPreference(next))
    preferenceState.saveDebounced()
  }

  /** 条件偏好变更后同步偏好。 */
  const commitFromTable = (): void => {
    commit(composePreference())
  }

  const rows = ref<unknown[]>([...table.rows])
  const total = ref(table.total)
  const page = ref(table.page)
  const pageSize = ref(table.pageSize)
  const sorts = ref<SortSpec[]>([...table.sorts])
  const listDensity = ref<TableDensity>(table.listDensity)
  const editable = ref(table.editable)
  const selectedKeys = ref<string[]>(table.selectedKeys)
  const summary = ref<SelectionSummary>(table.selection.summary)
  const expandedKeys = ref<string[]>([...table.expandedKeys].map((key) => String(key)))
  const columnPreferences = ref<ListPreference['columns']>(toColumnPreferences(table.columnConfig.columns))
  const revision = ref(0)

  /** 从基类实例同步响应式面（并递增变更序号，供非响应式实例态驱动的重算）。 */
  const sync = (): void => {
    revision.value += 1
    rows.value = [...table.rows]
    total.value = table.total
    page.value = table.page
    pageSize.value = table.pageSize
    sorts.value = [...table.sorts]
    listDensity.value = table.listDensity
    editable.value = table.editable
    selectedKeys.value = table.selectedKeys
    summary.value = table.selection.summary
    expandedKeys.value = [...table.expandedKeys].map((key) => String(key))
    columnPreferences.value = toColumnPreferences(table.columnConfig.columns)
  }

  const offTable = table.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  const offSelection = table.selection.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  const offColumns = table.columnConfig.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    offTable()
    offSelection()
    offColumns()
  })

  const visibleColumns = computed<TableColumn[]>(() => {
    void revision.value
    const state = new Map(table.columnConfig.columns.map((column) => [column.key, column]))
    const ordered = [...columns.value]
      .filter((column) => state.get(column.key)?.visible !== false)
      .sort((left, right) => (state.get(left.key)?.order ?? 0) - (state.get(right.key)?.order ?? 0))
    return ordered
  })

  /** 以偏好整份回填表状态（列 / 页长 / 密度）。 */
  const applyPreference = (value: unknown): void => {
    const pref = normalizeListPreference(value)
    table.columnConfig.setColumns(fromColumnPreferences(pref.columns, columns.value))
    table.setPageSize(pref.page_size)
    table.setListDensity(pref.density)
    preferenceState.setLocal(pref)
    sync()
  }

  if (options.formKey !== undefined && preferenceState.hasLocal.value) {
    applyPreference(preferenceState.local.value)
  }

  return {
    table,
    ready: placeholder.ready,
    degraded: placeholder.degraded,
    requestCount: placeholder.requestCount,
    rows,
    total,
    page,
    pageSize,
    sorts,
    listDensity,
    editable,
    columns,
    visibleColumns,
    selectedKeys,
    summary,
    expandedKeys,
    columnPreferences,
    preference,
    queryConditions: computed(() => preference.value.query.conditions),
    keyword: computed(() => preference.value.query.keyword ?? ''),
    oversized: computed(() => isListPreferenceOversized(preference.value)),
    revision,
    setReady: (value) => placeholder.setReady(value),
    markLoaded: () => placeholder.markLoaded(),
    setRows: (next, nextTotal) => {
      table.setRows(next, nextTotal)
      sync()
    },
    setPage: (next) => {
      table.setPage(next)
      sync()
    },
    setPageSize: (next) => {
      table.setPageSize(next)
      sync()
      commitFromTable()
    },
    resetToFirstPage: () => {
      table.resetToFirstPage()
      sync()
    },
    toggleSort: (column, additive) => {
      const result = table.toggleSort(column, additive)
      sync()
      return result
    },
    clearSort: () => {
      table.clearSort()
      sync()
    },
    setListDensity: (density) => {
      table.setListDensity(density)
      sync()
      commitFromTable()
    },
    setVisible: (key, visible) => {
      table.columnConfig.setVisible(key, visible)
      sync()
      commitFromTable()
    },
    moveColumn: (key, offset) => {
      table.columnConfig.moveColumn(key, offset)
      sync()
      commitFromTable()
    },
    setWidth: (key, width) => {
      table.columnConfig.setWidth(key, width)
      sync()
      commitFromTable()
    },
    resetColumns: () => {
      table.columnConfig.resetColumns(toSeeds(columns.value))
      sync()
      commitFromTable()
    },
    normalizeColumns: () => {
      table.columnConfig.normalizeWith(toSeeds(columns.value))
      sync()
      commitFromTable()
    },
    setColumns: (next) => {
      columns.value = mergeTableColumns(next)
      table.columnConfig.normalizeWith(toSeeds(columns.value))
      sync()
    },
    setSorts: (next) => {
      table.sorts.length = 0
      table.sorts.push(...next.map((item) => ({ ...item })))
      table.sort = table.sorts[0]
      sync()
    },
    toggleSelect: (key) => {
      table.toggleSelect(key)
      sync()
    },
    setRowKeys: (keys) => {
      table.setRowKeys(keys)
      sync()
    },
    selectAllAcrossPages: () => {
      table.selection.selectAllAcrossPages()
      sync()
    },
    clearSelection: () => {
      table.selection.clear()
      sync()
    },
    toggleExpand: (key) => {
      table.toggleExpand(key)
      sync()
    },
    expandAll: () => {
      table.expandAll()
      sync()
    },
    collapseAll: () => {
      table.collapseAll()
      sync()
    },
    setEditable: (value) => {
      table.setEditable(value)
      sync()
    },
    setQueryConditions: (conditions, keyword) => {
      commit(withQuery(composePreference(), conditions, keyword))
    },
    clearQuery: () => {
      commit(withoutQuery(composePreference()))
    },
    prunePreference: () => {
      const result = pruneListPreference(preference.value, options.fields ?? [], columns.value)
      commit(result.preference)
      return result.removedConditions
    },
    applyPreference,
  }
}
