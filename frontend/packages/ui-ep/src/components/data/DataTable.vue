<script setup lang="ts">
// 通用表格（07_05）：声明式列配置与渲染优先级 / 分页与多列排序 / 多选·展开·树形·行内编辑 / 虚拟滚动 /
// 列个性化持久化 / 工具栏与空·加载·错误三态。对外契约保持 07_01 冻结形状，仅向后兼容新增。
import {
  computeVirtualRange,
  formatAmount,
  formatDate,
  formatDateTime,
  formatFileSize,
  formatNumber,
  formatPercent,
  getBaseSinks,
  isVirtualEnabled,
  mask,
  measureAutoWidth,
  resolveRenderKind,
  rowKeyOf,
  type TableColumn,
  type TableColumnMeta,
  type TableDensity,
} from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseTable } from '../../composables/useBaseTable'
import { canFullscreen, enterFullscreen, exitFullscreen } from '../../utils/fullscreen'

import StatusTag from './StatusTag.vue'

/** 表格列定义（冻结契约；本次仅向后兼容新增可选字段）。 */
export interface DataTableColumn {
  /** 字段名。 */
  key: string
  /** 列头文案。 */
  title: string
  /** 固定列宽（px）。 */
  width?: number
  /** 是否参与排序。 */
  sortable?: boolean
  /** 最小宽度（自适应基准）。 */
  minWidth?: number
  /** 对齐。 */
  align?: 'left' | 'center' | 'right'
  /** 固定位置。 */
  fixed?: 'left' | 'right'
  /** 后端排序字段名。 */
  sortField?: string
  /** 溢出省略。 */
  ellipsis?: boolean
  /** 格式化口径。 */
  format?: 'number' | 'amount' | 'percent' | 'date' | 'datetime' | 'fileSize' | 'boolean'
  /** 字典类型（配合注入的翻译处理函数）。 */
  dictType?: string
  /** 是否状态列。 */
  status?: boolean
  /** 是否脱敏列。 */
  mask?: boolean
  /** 默认是否可见。 */
  visible?: boolean
  /** 行内编辑模式下是否可编辑（缺省按 `editable` 全列可编辑）。 */
  editable?: boolean
}

/** 排序状态（冻结契约）。 */
export interface DataTableSort {
  /** 字段名。 */
  prop: string
  /** 方向。 */
  order: 'asc' | 'desc'
}

/** 行内编辑变更载荷。 */
export interface DataTableCellChange {
  /** 行数据。 */
  row: Record<string, unknown>
  /** 列定义。 */
  column: DataTableColumn
  /** 新值。 */
  value: string
}

/** 虚拟滚动行高缺省值。 */
const VIRTUAL_ROW_HEIGHT = 44

/** 虚拟滚动缓冲行数。 */
const VIRTUAL_BUFFER = 4

interface Props {
  /** 数据通路是否就绪（缺省 false，占位零请求）。 */
  ready?: boolean
  /** 列定义。 */
  columns?: DataTableColumn[]
  /** 表单元数据列（为声明列提供默认）。 */
  columnMeta?: TableColumnMeta[]
  /** 行数据。 */
  data?: Record<string, unknown>[]
  /** 加载中。 */
  loading?: boolean
  /** 总条数。 */
  total?: number
  /** 当前页（从 1 起）。 */
  page?: number
  /** 每页条数。 */
  pageSize?: number
  /** 行主键字段。 */
  rowKey?: string
  /** 是否可多选。 */
  selectable?: boolean
  /** 是否可展开行。 */
  expandable?: boolean
  /** 是否树形模式。 */
  tree?: boolean
  /** 子节点字段。 */
  childrenKey?: string
  /** 默认展开全部（树形）。 */
  defaultExpandAll?: boolean
  /** 是否行内编辑模式。 */
  editable?: boolean
  /** 受控多列排序。 */
  sorts?: DataTableSort[]
  /** 列表密度。 */
  density?: TableDensity
  /** 是否虚拟滚动（阈值 200 行、定高、与树形 / 展开 / 行内编辑互斥）。 */
  virtual?: boolean
  /** 虚拟模式行高。 */
  rowHeight?: number
  /** 虚拟模式视口高度（px 数值）。 */
  virtualHeight?: number
  /** 是否展示工具栏。 */
  showToolbar?: boolean
  /** 是否展示分页区。 */
  showFooter?: boolean
  /** 列表偏好键标识（列个性化持久化）。 */
  formKey?: string
  /** 错误文案（有值即错误态）。 */
  error?: string
  /** 是否首屏加载（首屏骨架屏）。 */
  firstLoad?: boolean
  /** 是否处于筛选检索结果（搜索无结果文案）。 */
  searchActive?: boolean
  /** 空态文案。 */
  emptyText?: string
  /** 降级文案。 */
  degradeText?: string
  /** 是否具备查看明文权限（脱敏列）。 */
  plainEnabled?: boolean
  /** 字典 label 翻译（宿主注入；未注入即显示原值，不发请求）。 */
  translator?: (dictType: string, value: unknown) => string | undefined
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  columns: () => [],
  columnMeta: () => [],
  data: () => [],
  loading: false,
  total: 0,
  page: 1,
  pageSize: 20,
  rowKey: 'id',
  selectable: false,
  expandable: false,
  tree: false,
  childrenKey: 'children',
  defaultExpandAll: false,
  editable: false,
  sorts: () => [],
  density: 'default',
  virtual: false,
  rowHeight: VIRTUAL_ROW_HEIGHT,
  virtualHeight: 360,
  showToolbar: true,
  showFooter: true,
  formKey: undefined,
  error: '',
  firstLoad: false,
  searchActive: false,
  emptyText: '暂无数据',
  degradeText: '表格数据未就绪（占位）',
  plainEnabled: false,
  translator: undefined,
})

const emit = defineEmits<{
  'update:page': [page: number]
  'update:pageSize': [pageSize: number]
  'sort-change': [sort: DataTableSort]
  'selection-change': [keys: string[]]
  'row-click': [row: Record<string, unknown>]
  'sorts-change': [sorts: DataTableSort[]]
  'update:density': [density: TableDensity]
  'update:expanded': [keys: string[]]
  'expand-change': [keys: string[]]
  'row-dblclick': [row: Record<string, unknown>]
  'cell-change': [payload: DataTableCellChange]
  'column-change': [columns: { prop: string; visible: boolean; order: number; width?: number }[]]
  refresh: []
  retry: []
  'clear-filter': []
  'add-row': []
  'remove-row': [row: Record<string, unknown>]
  'move-row': [row: Record<string, unknown>, offset: number]
  'selection-summary': [payload: { count: number; total: number; allAcrossPages: boolean }]
}>()

const tableApi = useBaseTable({
  ready: props.ready,
  formKey: props.formKey,
  rowKey: props.rowKey,
  pageSize: props.pageSize,
  listDensity: props.density,
  tree: props.tree,
  childrenKey: props.childrenKey,
  editable: props.editable,
  columns: props.columns,
  columnMeta: props.columnMeta,
})

const rootRef = ref<HTMLElement>()
const settingsOpen = ref(false)
const fullscreen = ref(false)
const scrollTop = ref(0)
const viewportHeight = ref(props.virtualHeight)
const expandedRows = ref<string[]>([])
/** 是否已就虚拟模式冲突告警一次。 */
let conflictWarned = false

watch(
  () => props.ready,
  (next) => tableApi.setReady(next),
)

watch(
  () => [props.data, props.total] as const,
  ([rows, total]) => {
    tableApi.setRows(rows, total)
    if (props.defaultExpandAll && props.tree) {
      tableApi.expandAll()
      expandedRows.value = tableApi.expandedKeys.value
    }
  },
  { immediate: true },
)

watch(
  () => [props.columns, props.columnMeta] as const,
  () => tableApi.setColumns(props.columns),
)

watch(
  () => props.page,
  (next) => {
    if (next !== tableApi.page.value) {
      tableApi.setPage(next)
    }
  },
)

watch(
  () => props.pageSize,
  (next) => {
    if (next !== tableApi.pageSize.value) {
      tableApi.setPageSize(next)
    }
  },
)

watch(
  () => props.density,
  (next) => {
    if (next !== tableApi.listDensity.value) {
      tableApi.setListDensity(next)
    }
  },
)

watch(
  () => props.sorts,
  (next) => {
    if (next.length === 0) {
      return
    }
    tableApi.setSorts(next.map((item) => ({ field: item.prop, order: item.order })))
  },
  { immediate: true },
)

watch(
  () => props.virtualHeight,
  (next) => {
    viewportHeight.value = next
  },
)

/** 是否与虚拟模式互斥（树形 / 展开行 / 行内编辑）。 */
const virtualConflict = computed(() => props.tree || props.expandable || props.editable)

/** 是否启用虚拟模式（阈值与互斥口径）。 */
const virtualEnabled = computed(() => !virtualConflict.value && isVirtualEnabled(props.virtual, props.data.length))

watch(virtualEnabled, () => {
  if (props.virtual && virtualConflict.value && !conflictWarned) {
    conflictWarned = true
    getBaseSinks().logger('warn', 'DataTable：虚拟模式与树形 / 展开行 / 行内编辑互斥，已按普通模式渲染')
  }
})

/** 可见列（列声明 + 偏好状态；读变更序号以触发实例态驱动的重算）。 */
const visibleColumns = computed<DataTableColumn[]>(() => {
  void tableApi.revision.value
  const state = new Map(tableApi.table.columnConfig.columns.map((column) => [column.key, column]))
  return [...tableApi.columns.value]
    .filter((column) => state.get(column.key)?.visible !== false)
    .sort((left, right) => (state.get(left.key)?.order ?? 0) - (state.get(right.key)?.order ?? 0))
})

/** 展示行（树形展平或原始行）。 */
const displayRows = computed<{ row: Record<string, unknown>; key: string; level: number; hasChildren: boolean }[]>(
  () => {
    if (!props.tree) {
      return props.data.map((row) => ({ row, key: rowKeyOf(row, props.rowKey), level: 0, hasChildren: false }))
    }
    const state = new Set<string | number>(tableApi.expandedKeys.value)
    const result: { row: Record<string, unknown>; key: string; level: number; hasChildren: boolean }[] = []
    const walk = (rows: Record<string, unknown>[], level: number): void => {
      for (const row of rows) {
        const children = row[props.childrenKey]
        const list = Array.isArray(children) ? (children as Record<string, unknown>[]) : []
        const key = rowKeyOf(row, props.rowKey)
        result.push({ row, key, level, hasChildren: list.length > 0 })
        if (list.length > 0 && state.has(key)) {
          walk(list, level + 1)
        }
      }
    }
    walk(props.data, 0)
    return result
  },
)

/** 虚拟滚动区间。 */
const virtualRange = computed(() =>
  computeVirtualRange({
    scrollTop: scrollTop.value,
    viewportHeight: viewportHeight.value,
    count: displayRows.value.length,
    itemHeight: props.rowHeight,
    buffer: VIRTUAL_BUFFER,
  }),
)

/** 虚拟模式渲染行。 */
const virtualRows = computed(() =>
  displayRows.value
    .slice(virtualRange.value.start, virtualRange.value.end)
    .map((item, offset) => ({ ...item, index: virtualRange.value.start + offset })),
)

/** 是否展示首屏骨架屏。 */
const showSkeleton = computed(() => props.firstLoad && props.loading)

/** 是否展示内容遮罩。 */
const showOverlay = computed(() => props.loading && !props.firstLoad)

/** 是否错误态。 */
const hasError = computed(() => props.error !== '')

/** 是否空态。 */
const isEmptyState = computed(() => !props.loading && !hasError.value && displayRows.value.length === 0)

/** 选中摘要。 */
const summary = computed(() => tableApi.summary.value)

/** 是否已全选当前页。 */
const allSelected = computed(
  () =>
    displayRows.value.length > 0 && displayRows.value.every((item) => tableApi.selectedKeys.value.includes(item.key)),
)

/** 列宽（用户拖拽 / 自动列宽结果优先）。 */
function columnWidth(column: DataTableColumn): number | undefined {
  const state = tableApi.table.columnConfig.columns.find((item) => item.key === column.key)
  return state?.width ?? column.width
}

/** 列样式。 */
function columnStyle(column: DataTableColumn): Record<string, string> {
  const width = columnWidth(column)
  const minWidth = column.minWidth ?? column.width
  return {
    width: width === undefined ? 'auto' : `${width}px`,
    minWidth: minWidth === undefined ? 'auto' : `${minWidth}px`,
    textAlign: column.align ?? 'left',
  }
}

/** 排序优先级序号（未命中返回 0）。 */
function sortIndexOf(column: DataTableColumn): number {
  const field = column.sortField ?? column.key
  return tableApi.sorts.value.findIndex((item) => item.field === field) + 1
}

/** 单元格文本（空值统一占位）。 */
function cellText(row: Record<string, unknown>, column: DataTableColumn): string {
  const value = row[column.key]
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return String(value)
}

/** 格式化单元格文本。 */
function formattedText(row: Record<string, unknown>, column: DataTableColumn): string {
  const value = row[column.key]
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  switch (column.format) {
    case 'number':
      return formatNumber(Number(value))
    case 'amount':
      return formatAmount(Number(value))
    case 'percent':
      return formatPercent(Number(value))
    case 'date':
      return formatDate(String(value))
    case 'datetime':
      return formatDateTime(String(value))
    case 'fileSize':
      return formatFileSize(Number(value))
    case 'boolean':
      return value === true || value === 1 || value === '1' ? '是' : '否'
    default:
      return String(value)
  }
}

/** 渲染类型（优先级：字典 → 状态 → 脱敏 → 格式化 → 原值）。 */
function renderKindOf(column: DataTableColumn): string {
  return resolveRenderKind(column as TableColumn)
}

/** 脱敏文本。 */
function maskedText(row: Record<string, unknown>, column: DataTableColumn): string {
  if (props.plainEnabled) {
    return cellText(row, column)
  }
  return mask(cellText(row, column))
}

/** 字典翻译文本。 */
function dictText(row: Record<string, unknown>, column: DataTableColumn): string {
  const value = row[column.key]
  const translated = column.dictType === undefined ? undefined : props.translator?.(column.dictType, value)
  return translated ?? (value === null || value === undefined ? '—' : String(value))
}

/** 行是否展开。 */
function isRowExpanded(key: string): boolean {
  return expandedRows.value.includes(key)
}

/** 是否行内可编辑列。 */
function isEditableColumn(column: DataTableColumn): boolean {
  return props.editable && column.editable !== false
}

/**
 * 切换排序（Shift 叠加多列）。
 *
 * @param column 列定义。
 * @param event 鼠标事件。
 */
function onSort(column: DataTableColumn, event: MouseEvent): void {
  if (column.sortable !== true) {
    return
  }
  const result = tableApi.toggleSort(column as TableColumn, event.shiftKey)
  const list = result.map((item) => ({ prop: item.field, order: item.order }))
  emit('sorts-change', list)
  const primary = list[0] ?? { prop: column.sortField ?? column.key, order: 'asc' as const }
  emit('sort-change', primary)
}

/** 切换全选。 */
function toggleAll(): void {
  if (allSelected.value) {
    tableApi.clearSelection()
  } else {
    tableApi.setRowKeys(displayRows.value.map((item) => item.key))
    displayRows.value.forEach((item) => {
      if (!tableApi.selectedKeys.value.includes(item.key)) {
        tableApi.toggleSelect(item.key)
      }
    })
  }
  emit('selection-change', tableApi.selectedKeys.value)
  emit('selection-summary', summary.value)
}

/**
 * 切换单行选中。
 *
 * @param key 行键。
 */
function toggleRow(key: string): void {
  tableApi.toggleSelect(key)
  emit('selection-change', tableApi.selectedKeys.value)
  emit('selection-summary', summary.value)
}

/**
 * 切换行展开。
 *
 * @param key 行键。
 */
function toggleExpand(key: string): void {
  expandedRows.value = isRowExpanded(key)
    ? expandedRows.value.filter((item) => item !== key)
    : [...expandedRows.value, key]
  tableApi.toggleExpand(key)
  emit('update:expanded', expandedRows.value)
  emit('expand-change', expandedRows.value)
}

/**
 * 切换树形节点展开。
 *
 * @param key 行键。
 */
function toggleTree(key: string): void {
  tableApi.toggleExpand(key)
  emit('update:expanded', tableApi.expandedKeys.value)
  emit('expand-change', tableApi.expandedKeys.value)
}

/**
 * 单元格编辑变更。
 *
 * @param row 行数据。
 * @param column 列定义。
 * @param event 输入事件。
 */
function onCellInput(row: Record<string, unknown>, column: DataTableColumn, event: Event): void {
  emit('cell-change', { row, column, value: (event.target as HTMLInputElement).value })
}

/** 刷新（保留筛选、排序与分页）。 */
function onRefresh(): void {
  emit('refresh')
}

/** 分页上一页。 */
function onPrev(): void {
  tableApi.setPage(tableApi.page.value - 1)
  emit('update:page', tableApi.page.value)
}

/** 分页下一页。 */
function onNext(): void {
  tableApi.setPage(tableApi.page.value + 1)
  emit('update:page', tableApi.page.value)
}

/**
 * 切换密度并持久化。
 */
function onToggleDensity(): void {
  const next: TableDensity = tableApi.listDensity.value === 'small' ? 'default' : 'small'
  tableApi.setListDensity(next)
  emit('update:density', next)
  emit('column-change', tableApi.columnPreferences.value)
}

/** 切换列设置抽屉。 */
function onToggleSettings(): void {
  settingsOpen.value = !settingsOpen.value
}

/**
 * 切换列显隐并持久化。
 *
 * @param key 列键。
 */
function onToggleColumn(key: string): void {
  const state = tableApi.table.columnConfig.columns.find((column) => column.key === key)
  tableApi.setVisible(key, state?.visible !== true)
  emit('column-change', tableApi.columnPreferences.value)
}

/**
 * 移动列并持久化。
 *
 * @param key 列键。
 * @param offset 偏移。
 */
function onMoveColumn(key: string, offset: number): void {
  tableApi.moveColumn(key, offset)
  emit('column-change', tableApi.columnPreferences.value)
}

/**
 * 重置列宽并持久化。
 *
 * @param key 列键。
 */
function onResetColumnWidth(key: string): void {
  const seed = tableApi.columns.value.find((column) => column.key === key)
  tableApi.setWidth(key, seed?.width ?? 160)
  emit('column-change', tableApi.columnPreferences.value)
}

/** 恢复默认列配置并持久化。 */
function onResetColumns(): void {
  tableApi.resetColumns()
  emit('column-change', tableApi.columnPreferences.value)
}

/** 自动列宽（用户拖拽过的列由宽度状态保留，不被覆盖）。 */
function onAutoWidth(): void {
  for (const column of visibleColumns.value) {
    tableApi.setWidth(column.key, measureAutoWidth(column.title, props.data, column.key))
  }
  emit('column-change', tableApi.columnPreferences.value)
}

/** 切换全屏（能力缺失或被拒时降级为固定铺满）。 */
function onToggleFullscreen(): void {
  const element = rootRef.value
  fullscreen.value = !fullscreen.value
  if (fullscreen.value) {
    if (element !== undefined && canFullscreen(element)) {
      void enterFullscreen(element).catch(() => {
        fullscreen.value = true
      })
    }
    return
  }
  void exitFullscreen()
}

/**
 * 虚拟滚动事件。
 *
 * @param event 滚动事件。
 */
function onVirtualScroll(event: Event): void {
  const target = event.target as HTMLElement
  scrollTop.value = target.scrollTop
  viewportHeight.value = target.clientHeight
}

/** 虚拟行样式。 */
function virtualRowStyle(index: number): Record<string, string> {
  return {
    position: 'absolute',
    top: `${index * props.rowHeight}px`,
    left: '0',
    right: '0',
    height: `${props.rowHeight}px`,
  }
}
</script>

<template>
  <div
    ref="rootRef"
    class="bms-data-table"
    :class="fullscreen ? 'is-fullscreen' : ''"
    data-test="data-table-root"
    :data-ready="tableApi.ready.value"
    :data-degraded="tableApi.degraded.value"
    :data-density="tableApi.table.densityToken"
  >
    <slot v-if="tableApi.degraded.value" name="degrade">
      <div class="bms-display-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <div v-if="showToolbar" class="bms-data-table__toolbar" data-test="toolbar">
        <button type="button" data-test="refresh" @click="onRefresh">刷新</button>
        <button type="button" data-test="density" @click="onToggleDensity">密度</button>
        <button type="button" data-test="column-settings" @click="onToggleSettings">列设置</button>
        <button type="button" data-test="fullscreen" @click="onToggleFullscreen">全屏</button>
        <button type="button" data-test="auto-width" @click="onAutoWidth">自动列宽</button>
        <slot name="toolbar" />
      </div>

      <div v-if="settingsOpen" class="bms-data-table__settings" data-test="settings-panel">
        <div
          v-for="column in tableApi.columns.value"
          :key="column.key"
          class="bms-data-table__settings-item"
          :data-test="`settings-item-${column.key}`"
        >
          <input
            type="checkbox"
            :checked="tableApi.table.columnConfig.columns.find((item) => item.key === column.key)?.visible !== false"
            :data-test="`settings-visible-${column.key}`"
            @change="onToggleColumn(column.key)"
          />
          <span>{{ column.title }}</span>
          <button type="button" :data-test="`settings-move-${column.key}`" @click="onMoveColumn(column.key, -1)">
            上移
          </button>
          <button type="button" @click="onMoveColumn(column.key, 1)">下移</button>
          <button
            type="button"
            :data-test="`settings-width-reset-${column.key}`"
            @click="onResetColumnWidth(column.key)"
          >
            重置列宽
          </button>
        </div>
        <button type="button" data-test="settings-reset" @click="onResetColumns">恢复默认</button>
        <slot name="column-settings" />
      </div>

      <div v-if="showSkeleton" class="bms-data-table__skeleton" data-test="skeleton">
        <div v-for="index in 3" :key="index" class="bms-data-table__skeleton-row" />
      </div>

      <template v-else-if="hasError">
        <div class="bms-data-table__error" data-test="error">
          <slot name="error" :message="error">{{ error }}</slot>
          <button type="button" data-test="retry" @click="emit('retry')">重试</button>
        </div>
      </template>

      <template v-else-if="isEmptyState">
        <div class="bms-data-table__empty" data-test="empty">
          <slot name="empty">
            <span v-if="searchActive">未找到相关内容</span>
            <span v-else>{{ emptyText }}</span>
          </slot>
          <button v-if="searchActive" type="button" data-test="empty-clear" @click="emit('clear-filter')">
            清除筛选
          </button>
        </div>
      </template>

      <template v-else-if="virtualEnabled">
        <div class="bms-data-table__header" data-test="virtual-header">
          <span v-if="selectable" class="bms-data-table__cell--check">
            <input type="checkbox" data-test="select-all" :checked="allSelected" @change="toggleAll" />
          </span>
          <span v-for="column in visibleColumns" :key="column.key" :style="columnStyle(column)">{{
            column.title
          }}</span>
        </div>
        <div
          class="bms-data-table__virtual"
          data-test="virtual-scroll"
          :style="{ height: `${virtualHeight}px` }"
          @scroll="onVirtualScroll"
        >
          <div class="bms-data-table__virtual-spacer" :style="{ height: `${virtualRange.totalHeight}px` }">
            <div
              v-for="item in virtualRows"
              :key="item.key"
              class="bms-data-table__virtual-row"
              :data-test="`row-${item.key}`"
              :style="virtualRowStyle(item.index)"
              @click="emit('row-click', item.row)"
            >
              <span v-for="column in visibleColumns" :key="column.key" :style="columnStyle(column)">
                <slot :name="`cell-${column.key}`" :row="item.row" :column="column">{{
                  cellText(item.row, column)
                }}</slot>
              </span>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <table class="bms-data-table__table" data-test="data-table">
          <thead>
            <tr>
              <th v-if="selectable" class="bms-data-table__cell--check">
                <input type="checkbox" data-test="select-all" :checked="allSelected" @change="toggleAll" />
              </th>
              <th
                v-for="column in visibleColumns"
                :key="column.key"
                :style="columnStyle(column)"
                :data-sortable="column.sortable || undefined"
                @click="onSort(column, $event)"
              >
                {{ column.title }}
                <span
                  v-if="sortIndexOf(column) > 0"
                  :data-test="`sort-index-${column.key}`"
                  class="bms-data-table__sort-index"
                >
                  {{ sortIndexOf(column) }}
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="item in displayRows" :key="item.key">
              <tr
                :data-test="`row-${item.key}`"
                @click="emit('row-click', item.row)"
                @dblclick="emit('row-dblclick', item.row)"
              >
                <td v-if="selectable" class="bms-data-table__cell--check">
                  <input
                    type="checkbox"
                    :checked="tableApi.selectedKeys.value.includes(item.key)"
                    @click.stop
                    @change="toggleRow(item.key)"
                  />
                </td>
                <td v-for="(column, columnIndex) in visibleColumns" :key="column.key" :style="columnStyle(column)">
                  <template v-if="columnIndex === 0 && tree">
                    <span class="bms-data-table__indent" :style="{ paddingLeft: `${item.level * 16}px` }" />
                    <button
                      v-if="item.hasChildren"
                      type="button"
                      :data-test="`tree-toggle-${item.key}`"
                      @click.stop="toggleTree(item.key)"
                    >
                      {{ tableApi.expandedKeys.value.includes(item.key) ? '▾' : '▸' }}
                    </button>
                  </template>
                  <template v-if="columnIndex === 0 && expandable">
                    <button type="button" :data-test="`expand-toggle-${item.key}`" @click.stop="toggleExpand(item.key)">
                      {{ isRowExpanded(item.key) ? '▾' : '▸' }}
                    </button>
                  </template>
                  <input
                    v-if="isEditableColumn(column)"
                    :data-test="`cell-input-${item.key}-${column.key}`"
                    :value="cellText(item.row, column)"
                    @click.stop
                    @change="onCellInput(item.row, column, $event)"
                  />
                  <slot v-else :name="`cell-${column.key}`" :row="item.row" :column="column">
                    <StatusTag
                      v-if="renderKindOf(column) === 'status'"
                      :value="cellText(item.row, column)"
                      size="small"
                    />
                    <span v-else-if="renderKindOf(column) === 'dict'">{{ dictText(item.row, column) }}</span>
                    <span v-else-if="renderKindOf(column) === 'mask'">{{ maskedText(item.row, column) }}</span>
                    <span v-else-if="renderKindOf(column) === 'format'">{{ formattedText(item.row, column) }}</span>
                    <span v-else>{{ cellText(item.row, column) }}</span>
                  </slot>
                </td>
              </tr>
              <tr v-if="expandable && isRowExpanded(item.key)" :data-test="`expanded-${item.key}`">
                <td :colspan="visibleColumns.length + (selectable ? 1 : 0)">
                  <slot name="expand" :row="item.row" />
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div v-if="showOverlay" class="bms-data-table__overlay" data-test="overlay">加载中…</div>
      </template>

      <div v-if="selectable" class="bms-data-table__summary" data-test="selection-summary">
        已选 {{ summary.count }} 条
      </div>

      <div v-if="showFooter" class="bms-data-table__footer" data-test="footer">
        <slot name="footer-left" />
        <span data-test="total">共 {{ total }} 条</span>
        <button type="button" data-test="prev" :disabled="page <= 1" @click="onPrev">上一页</button>
        <span data-test="page">{{ page }}</span>
        <button type="button" data-test="next" :disabled="total > 0 && page * pageSize >= total" @click="onNext">
          下一页
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bms-data-table {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size);
}

.bms-data-table.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 10;
  padding: var(--bms-spacing-lg);
  background: var(--bms-color-bg);
}

.bms-data-table__toolbar,
.bms-data-table__footer {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
}

.bms-data-table__footer {
  justify-content: flex-end;
}

.bms-data-table__toolbar button,
.bms-data-table__footer button,
.bms-data-table__error button,
.bms-data-table__empty button {
  height: var(--bms-control-height);
  padding: 0 var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm);
  background: var(--bms-color-bg);
  color: var(--bms-color-text);
  cursor: pointer;
}

.bms-data-table__table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.bms-data-table__table th {
  padding: var(--bms-spacing-md);
  border-bottom: 1px solid var(--bms-table-border);
  background: var(--bms-table-header-bg);
  color: var(--bms-color-text-secondary);
  font-weight: 600;
  text-align: left;
  cursor: default;
}

.bms-data-table__table th[data-sortable] {
  cursor: pointer;
}

.bms-data-table__table td {
  padding: var(--bms-spacing-md);
  border-bottom: 1px solid var(--bms-table-border);
}

.bms-data-table__table tbody tr:hover td {
  background: var(--bms-table-row-hover-bg);
}

.bms-data-table__table tbody tr:nth-child(even) td {
  background: var(--bms-table-zebra-bg);
}

.bms-data-table__sort-index {
  margin-left: var(--bms-spacing-sm);
  color: var(--bms-color-primary);
}

.bms-data-table__indent {
  display: inline-block;
}

.bms-data-table__settings {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
  padding: var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-data-table__settings-item {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
}

.bms-data-table__header,
.bms-data-table__virtual-row {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
  padding: 0 var(--bms-spacing-sm);
}

.bms-data-table__header {
  height: var(--bms-control-height);
  border-bottom: 1px solid var(--bms-table-border);
  background: var(--bms-table-header-bg);
  color: var(--bms-color-text-secondary);
  font-weight: 600;
}

.bms-data-table__header span,
.bms-data-table__virtual-row span {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-data-table__virtual {
  position: relative;
  overflow: auto;
  border-bottom: 1px solid var(--bms-table-border);
}

.bms-data-table__virtual-spacer {
  position: relative;
  width: 100%;
}

.bms-data-table__virtual-row {
  cursor: pointer;
}

.bms-data-table__virtual-row:hover {
  background: var(--bms-table-row-hover-bg);
}

.bms-data-table__overlay,
.bms-data-table__placeholder {
  color: var(--bms-color-text-secondary);
}

.bms-data-table__error {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md);
  color: var(--bms-color-danger);
}

.bms-data-table__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--bms-spacing-md);
  padding: var(--bms-spacing-lg);
  color: var(--bms-color-text-secondary);
}

.bms-data-table__skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
}

.bms-data-table__skeleton-row {
  height: var(--bms-control-height);
  border-radius: var(--bms-radius-sm);
  background: var(--bms-table-zebra-bg);
}

.bms-data-table__summary {
  color: var(--bms-color-text-secondary);
}
</style>
