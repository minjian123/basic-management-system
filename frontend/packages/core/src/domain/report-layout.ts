/**
 * 领域纯函数：报表设计器领域模型（图表项 / 12 列网格布局 / 序列化 / 校验 / 脏比对）。
 *
 * 设计态、报表查看页与保存载荷共用同一结构；框架无关、不触 DOM、不请求、不依赖第三方库，
 * 同输入同输出。图表配置沿用 `domain/chart.ts` 的 `ChartConfig` 口径。
 */

import { defaultMapping, normalizeChartConfig, normalizeChartKind, type ChartConfig, type ChartField } from './chart'
import { stableStringify } from './serialize'

/** 报表设计权限码。 */
export const REPORT_DESIGN_PERM = 'rpt:design'
/** 报表查看权限码。 */
export const REPORT_VIEW_PERM = 'rpt:view'
/** 报表设计器占位文案（数据通路未就绪）。 */
export const REPORT_DESIGNER_PLACEHOLDER_TEXT = '报表设计器未就绪（占位）'
/** 网格列数。 */
export const REPORT_GRID_COLUMNS = 12
/** 图表卡默认尺寸。 */
export const REPORT_DEFAULT_CELL = { w: 6, h: 4 }
/** 图表卡最小尺寸。 */
export const REPORT_MIN_CELL = { w: 2, h: 2 }
/** 图表卡最大尺寸。 */
export const REPORT_MAX_CELL = { w: 12, h: 12 }

/** 数据集字段。 */
export interface ReportField {
  /** 字段名。 */
  name: string
  /** 字段类型。 */
  type: string
}

/** 数据集声明的参数（设计态可填样例值预览）。 */
export interface ReportDatasetParam {
  /** 参数名。 */
  name: string
  /** 参数标签。 */
  label?: string
  /** 样例默认值。 */
  defaultValue?: unknown
}

/** 数据集（与 `08_01_03` 冻结契约同形）。 */
export interface ReportDataset {
  /** 数据集标识。 */
  id: string
  /** 数据集编码。 */
  code: string
  /** 数据集名称。 */
  name: string
  /** 状态。 */
  status: 'enabled' | 'disabled'
  /** 字段清单（数据映射用）。 */
  fields?: ReportField[]
  /** 参数声明（可选）。 */
  params?: ReportDatasetParam[]
}

/** 图表项（与 `08_01_03` 冻结契约同形；`config` 为 `ChartConfig`）。 */
export interface ReportChartItem {
  /** 图表项标识。 */
  id: string
  /** 引用数据集标识。 */
  datasetId: string
  /** 图表类型。 */
  chartType: string
  /** 标题。 */
  title?: string
  /** 图表配置覆盖。 */
  config?: Record<string, unknown>
  /** 网格布局坐标与尺寸。 */
  layout: { x: number; y: number; w: number; h: number }
}

/** 报表定义（保存载荷）。 */
export interface ReportDefinition {
  /** 报表编码。 */
  code: string
  /** 报表名称。 */
  name: string
  /** 图表项。 */
  charts: ReportChartItem[]
}

/** 校验问题种类。 */
export type ReportIssueKind =
  | 'empty'
  | 'unknown-dataset'
  | 'disabled-dataset'
  | 'missing-mapping'
  | 'invalid-config'
  | 'overlap'

/** 校验问题。 */
export interface ReportValidationIssue {
  /** 问题种类。 */
  kind: ReportIssueKind
  /** 涉事图表项（空报表无）。 */
  chartId?: string
  /** 说明。 */
  message: string
}

/** 校验结果。 */
export interface ReportValidationResult {
  /** 是否通过（重叠为警告，不阻断）。 */
  valid: boolean
  /** 问题清单。 */
  errors: ReportValidationIssue[]
  /** 汇总文案。 */
  message: string
}

/**
 * 归一网格尺寸（夹取到 min/max 并取整）。
 *
 * @param input 待归一尺寸。
 * @returns 归一尺寸。
 */
export function normalizeCell(input: unknown): { w: number; h: number } {
  const record = (input ?? {}) as { w?: unknown; h?: unknown }
  const w = clampInt(record.w, REPORT_MIN_CELL.w, REPORT_MAX_CELL.w, REPORT_DEFAULT_CELL.w)
  const h = clampInt(record.h, REPORT_MIN_CELL.h, REPORT_MAX_CELL.h, REPORT_DEFAULT_CELL.h)
  return { w, h }
}

/**
 * 取整并夹取到区间。
 *
 * @param value 待夹取值。
 * @param min 下限。
 * @param max 上限。
 * @param fallback 缺省值。
 * @returns 夹取结果。
 */
function clampInt(value: unknown, min: number, max: number, fallback: number): number {
  const num = typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : fallback
  return Math.min(Math.max(num, min), max)
}

/**
 * 归一图表项（脏引用不抛错）。
 *
 * @param value 待归一值。
 * @param fieldsByDataset 数据集字段映射（校验图表类型可选）。
 * @returns 归一图表项（缺标识返回 `undefined`）。
 */
export function normalizeChartItem(
  value: unknown,
  fieldsByDataset: Record<string, readonly ReportField[]> = {},
): ReportChartItem | undefined {
  const record = (value ?? {}) as Partial<ReportChartItem>
  const id = typeof record.id === 'string' && record.id !== '' ? record.id : undefined
  if (id === undefined) {
    return undefined
  }
  const datasetId = typeof record.datasetId === 'string' ? record.datasetId : ''
  const kind = normalizeChartKind(record.chartType)
  const cell = normalizeCell(record.layout)
  const x = clampInt((record.layout as { x?: unknown } | undefined)?.x, 0, REPORT_GRID_COLUMNS - cell.w, 0)
  const y = clampInt((record.layout as { y?: unknown } | undefined)?.y, 0, Number.MAX_SAFE_INTEGER, 0)
  void fieldsByDataset
  return {
    id,
    datasetId,
    chartType: kind,
    ...(typeof record.title === 'string' && record.title !== '' ? { title: record.title } : {}),
    ...(record.config !== undefined && record.config !== null && typeof record.config === 'object'
      ? { config: { ...(record.config as Record<string, unknown>) } }
      : {}),
    layout: { x, y, w: cell.w, h: cell.h },
  }
}

/**
 * 归一图表项清单（剔除无标识项，保留顺序）。
 *
 * @param value 待归一值。
 * @param fieldsByDataset 数据集字段映射。
 * @returns 归一图表项清单。
 */
export function normalizeReportCharts(
  value: unknown,
  fieldsByDataset: Record<string, readonly ReportField[]> = {},
): ReportChartItem[] {
  if (!Array.isArray(value)) {
    return []
  }
  const items: ReportChartItem[] = []
  for (const entry of value) {
    const item = normalizeChartItem(entry, fieldsByDataset)
    if (item !== undefined) {
      items.push(item)
    }
  }
  return items
}

/**
 * 生成下一个图表项标识（`chart-{n}` 递增不冲突）。
 *
 * @param items 现有图表项。
 * @returns 新标识。
 */
export function nextChartId(items: readonly ReportChartItem[]): string {
  const used = new Set(items.map((item) => item.id))
  let index = items.length + 1
  while (used.has(`chart-${index}`)) {
    index += 1
  }
  return `chart-${index}`
}

/**
 * 该项与其它项是否网格重叠。
 *
 * @param items 图表项清单。
 * @param id 目标标识。
 * @returns 是否重叠。
 */
export function hasOverlap(items: readonly ReportChartItem[], id: string): boolean {
  const target = findChartItem(items, id)
  if (target === undefined) {
    return false
  }
  return items.some((item) => item.id !== id && rectanglesOverlap(target.layout, item.layout))
}

/**
 * 两矩形是否相交。
 *
 * @param a 矩形甲。
 * @param b 矩形乙。
 * @returns 是否相交。
 */
function rectanglesOverlap(
  a: { x: number; y: number; w: number; h: number },
  b: { x: number; y: number; w: number; h: number },
): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
}

/**
 * 查找图表项。
 *
 * @param items 图表项清单。
 * @param id 标识。
 * @returns 图表项（不存在 `undefined`）。
 */
export function findChartItem(items: readonly ReportChartItem[], id: string): ReportChartItem | undefined {
  return items.find((item) => item.id === id)
}

/**
 * 统计图表项数。
 *
 * @param items 图表项清单。
 * @returns 数量。
 */
export function countCharts(items: readonly ReportChartItem[]): number {
  return items.length
}

/**
 * 收集被引用的数据集标识（去重保序）。
 *
 * @param items 图表项清单。
 * @returns 数据集标识清单。
 */
export function collectUsedDatasets(items: readonly ReportChartItem[]): string[] {
  const result: string[] = []
  for (const item of items) {
    if (item.datasetId !== '' && !result.includes(item.datasetId)) {
      result.push(item.datasetId)
    }
  }
  return result
}

/**
 * 取数据集字段清单。
 *
 * @param datasets 数据集清单。
 * @param datasetId 数据集标识。
 * @returns 字段清单（不存在返回空数组）。
 */
export function fieldsOf(datasets: readonly ReportDataset[], datasetId: string): ReportField[] {
  const dataset = datasets.find((entry) => entry.id === datasetId)
  return dataset?.fields !== undefined ? [...dataset.fields] : []
}

/**
 * 数据集选项（停用置 `disabled`）。
 *
 * @param datasets 数据集清单。
 * @returns 选项清单。
 */
export function datasetOptions(datasets: readonly ReportDataset[]): { value: string; label: string; disabled: boolean }[] {
  return datasets.map((dataset) => ({
    value: dataset.id,
    label: `${dataset.name}（${dataset.code}）`,
    disabled: dataset.status !== 'enabled',
  }))
}

/**
 * 由图表项 + 字段清单生成默认配置。
 *
 * @param item 图表项。
 * @param fields 字段清单。
 * @returns 归一图表配置。
 */
export function buildItemConfig(item: ReportChartItem, fields: readonly ReportField[]): ChartConfig {
  const existing = item.config as unknown as Partial<ChartConfig> | undefined
  if (existing !== undefined && existing.chartType !== undefined) {
    return normalizeChartConfig({ ...existing, chartType: normalizeChartKind(item.chartType) }, fields as ChartField[])
  }
  return normalizeChartConfig(
    {
      chartType: normalizeChartKind(item.chartType),
      ...(item.title !== undefined ? { title: item.title } : {}),
      mapping: defaultMapping(fields as ChartField[]),
    },
    fields as ChartField[],
  )
}

/**
 * 解析图表标题（缺省 `图表 {id}`）。
 *
 * @param item 图表项。
 * @returns 标题。
 */
export function resolveChartTitle(item: ReportChartItem): string {
  return item.title !== undefined && item.title !== '' ? item.title : `图表 ${item.id}`
}

/**
 * 在网格内寻找首个可放下 `cell` 的位置。
 *
 * @param items 现有图表项。
 * @param cell 尺寸。
 * @returns 位置。
 */
function findFreeSpot(items: readonly ReportChartItem[], cell: { w: number; h: number }): { x: number; y: number } {
  for (let y = 0; y < 1000; y += 1) {
    for (let x = 0; x <= REPORT_GRID_COLUMNS - cell.w; x += 1) {
      const candidate = { x, y, w: cell.w, h: cell.h }
      if (!items.some((item) => rectanglesOverlap(candidate, item.layout))) {
        return { x, y }
      }
    }
  }
  return { x: 0, y: items.reduce((max, item) => Math.max(max, item.layout.y + item.layout.h), 0) }
}

/**
 * 新增图表项（不可变；自动落位）。
 *
 * @param items 现有图表项。
 * @param input 新增入参。
 * @returns 新图表项清单。
 */
export function addChartItem(
  items: readonly ReportChartItem[],
  input: { datasetId: string; chartType?: string; id?: string },
): ReportChartItem[] {
  const id = input.id !== undefined && input.id !== '' ? input.id : nextChartId(items)
  const cell = { ...REPORT_DEFAULT_CELL }
  const spot = findFreeSpot(items, cell)
  const item: ReportChartItem = {
    id,
    datasetId: input.datasetId,
    chartType: normalizeChartKind(input.chartType),
    title: `图表 ${id}`,
    layout: { x: spot.x, y: spot.y, w: cell.w, h: cell.h },
  }
  return [...items, item]
}

/**
 * 移除图表项（幂等）。
 *
 * @param items 图表项清单。
 * @param id 标识。
 * @returns 新图表项清单。
 */
export function removeChartItem(items: readonly ReportChartItem[], id: string): ReportChartItem[] {
  return items.filter((item) => item.id !== id)
}

/**
 * 更新图表项（标题 / 类型 / 配置）。
 *
 * @param items 图表项清单。
 * @param id 标识。
 * @param patch 变更。
 * @returns 新图表项清单。
 */
export function updateChartItem(
  items: readonly ReportChartItem[],
  id: string,
  patch: { title?: string; config?: Record<string, unknown>; chartType?: string },
): ReportChartItem[] {
  return items.map((item) => {
    if (item.id !== id) {
      return item
    }
    return {
      ...item,
      ...(patch.title !== undefined ? { title: patch.title } : {}),
      ...(patch.chartType !== undefined ? { chartType: normalizeChartKind(patch.chartType) } : {}),
      ...(patch.config !== undefined ? { config: { ...patch.config } } : {}),
    }
  })
}

/**
 * 移动图表项（夹取到网格内）。
 *
 * @param items 图表项清单。
 * @param id 标识。
 * @param x 目标列。
 * @param y 目标行。
 * @returns 新图表项清单。
 */
export function moveChartItem(items: readonly ReportChartItem[], id: string, x: number, y: number): ReportChartItem[] {
  return items.map((item) => {
    if (item.id !== id) {
      return item
    }
    return {
      ...item,
      layout: {
        ...item.layout,
        x: clampInt(x, 0, REPORT_GRID_COLUMNS - item.layout.w, item.layout.x),
        y: clampInt(y, 0, Number.MAX_SAFE_INTEGER, item.layout.y),
      },
    }
  })
}

/**
 * 缩放图表项（尺寸夹取并按新宽度夹取 x）。
 *
 * @param items 图表项清单。
 * @param id 标识。
 * @param w 宽（列）。
 * @param h 高（行）。
 * @returns 新图表项清单。
 */
export function resizeChartItem(items: readonly ReportChartItem[], id: string, w: number, h: number): ReportChartItem[] {
  return items.map((item) => {
    if (item.id !== id) {
      return item
    }
    const cell = normalizeCell({ w, h })
    return {
      ...item,
      layout: {
        x: clampInt(item.layout.x, 0, REPORT_GRID_COLUMNS - cell.w, 0),
        y: item.layout.y,
        w: cell.w,
        h: cell.h,
      },
    }
  })
}

/**
 * 居中图表项。
 *
 * @param items 图表项清单。
 * @param id 标识。
 * @returns 新图表项清单。
 */
export function centerChartItem(items: readonly ReportChartItem[], id: string): ReportChartItem[] {
  return items.map((item) => {
    if (item.id !== id) {
      return item
    }
    return { ...item, layout: { ...item.layout, x: Math.floor((REPORT_GRID_COLUMNS - item.layout.w) / 2) } }
  })
}

/**
 * 复制图表项（新标识 + 偏移落位）。
 *
 * @param items 图表项清单。
 * @param id 标识。
 * @returns 新图表项清单。
 */
export function duplicateChartItem(items: readonly ReportChartItem[], id: string): ReportChartItem[] {
  const source = findChartItem(items, id)
  if (source === undefined) {
    return [...items]
  }
  const newId = nextChartId(items)
  const spot = findFreeSpot(items, { w: source.layout.w, h: source.layout.h })
  const copy: ReportChartItem = {
    ...source,
    id: newId,
    title: source.title !== undefined ? `${source.title} 副本` : `图表 ${newId}`,
    ...(source.config !== undefined ? { config: { ...source.config } } : {}),
    layout: { x: spot.x, y: spot.y, w: source.layout.w, h: source.layout.h },
  }
  return [...items, copy]
}

/**
 * 校验图表项清单。
 *
 * @param items 图表项清单。
 * @param datasets 数据集清单。
 * @returns 校验结果（重叠为警告，不阻断）。
 */
export function validateReport(
  items: readonly ReportChartItem[],
  datasets: readonly ReportDataset[],
): ReportValidationResult {
  const errors: ReportValidationIssue[] = []
  if (items.length === 0) {
    errors.push({ kind: 'empty', message: '空报表：请先添加图表' })
  }
  const datasetMap = new Map(datasets.map((dataset) => [dataset.id, dataset]))
  for (const item of items) {
    const dataset = datasetMap.get(item.datasetId)
    if (dataset === undefined) {
      errors.push({ kind: 'unknown-dataset', chartId: item.id, message: `图表项 ${item.id} 引用的数据集不存在` })
    } else if (dataset.status !== 'enabled') {
      errors.push({ kind: 'disabled-dataset', chartId: item.id, message: `图表项 ${item.id} 引用的数据集已停用` })
    }
    const config = item.config as unknown as Partial<ChartConfig> | undefined
    if (config !== undefined && config.mapping !== undefined) {
      const metrics = config.mapping.metrics ?? []
      if (item.chartType !== 'table' && metrics.length === 0) {
        errors.push({ kind: 'missing-mapping', chartId: item.id, message: `图表项 ${item.id} 缺少度量映射` })
      }
    }
    if (hasOverlap(items, item.id)) {
      errors.push({ kind: 'overlap', chartId: item.id, message: `图表项 ${item.id} 与其它图表重叠（警告）` })
    }
  }
  const blocking = errors.filter((issue) => issue.kind !== 'overlap')
  return {
    valid: blocking.length === 0,
    errors,
    message: blocking.length === 0 ? '校验通过' : blocking.map((issue) => issue.message).join('；'),
  }
}

/**
 * 序列化图表项布局（稳定结构）。
 *
 * @param items 图表项清单。
 * @returns 布局结构。
 */
export function serializeReportLayout(items: readonly ReportChartItem[]): Record<string, unknown> {
  return {
    version: 1,
    columns: REPORT_GRID_COLUMNS,
    items: items.map((item) => ({ id: item.id, x: item.layout.x, y: item.layout.y, w: item.layout.w, h: item.layout.h })),
  }
}

/**
 * 序列化图表配置集（稳定结构）。
 *
 * @param items 图表项清单。
 * @returns 配置结构。
 */
export function serializeChartConfigs(items: readonly ReportChartItem[]): Record<string, unknown> {
  return {
    version: 1,
    items: items.map((item) => ({
      id: item.id,
      datasetId: item.datasetId,
      chartType: item.chartType,
      title: item.title ?? '',
      config: item.config ?? {},
    })),
  }
}

/**
 * 序列化报表定义（覆盖式提交载荷）。
 *
 * @param code 报表编码。
 * @param name 报表名称。
 * @param items 图表项清单。
 * @returns 稳定 JSON 字符串。
 */
export function serializeReport(code: string, name: string, items: readonly ReportChartItem[]): string {
  return stableStringify({
    code,
    name,
    chart_configs: serializeChartConfigs(items),
    layout: serializeReportLayout(items),
  })
}

/**
 * 图表项集是否等价（键序无关）。
 *
 * @param a 图表项集甲。
 * @param b 图表项集乙。
 * @returns 是否等价。
 */
export function reportChartsEqual(a: readonly ReportChartItem[], b: readonly ReportChartItem[]): boolean {
  return stableStringify(a) === stableStringify(b)
}

/**
 * 是否脏（与基线比对；基线缺失视为不脏）。
 *
 * @param current 当前图表项集。
 * @param baseline 基线图表项集。
 * @returns 是否脏。
 */
export function isReportDirty(
  current: readonly ReportChartItem[],
  baseline: readonly ReportChartItem[] | undefined,
): boolean {
  if (baseline === undefined) {
    return false
  }
  return !reportChartsEqual(current, baseline)
}
