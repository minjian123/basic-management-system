/**
 * 领域纯函数：打印（纸张 / 行容量 / 预分页 / 字段分行 / 汇总 / 页脚 / 色调 / 单元格格式化 / 样式变量名）。
 *
 * 打印数据模型（模板 / 字段 / 明细列 / 页）与分页算法下沉核心：框架无关、跨端与宿主共用，
 * 预览与导出（含服务端）以同一份分页结果为准，保证「所见即所打印」。
 * **不含色值与尺寸字面量**——打印样式经变量名（`--bms-print-*`）由宿主令牌注入。
 */

import { EMPTY_PLACEHOLDER, formatAmount, formatDate, formatDateTime, formatNumber, type FormatContext } from './format'

/** 纸张名。 */
export type PaperName = 'A4' | 'A5' | 'custom'

/** 纸张方向。 */
export type PaperOrientation = 'portrait' | 'landscape'

/** 打印色调。 */
export type PrintTone = 'color' | 'mono'

/** 纸张尺寸（毫米）。 */
export interface PaperSize {
  /** 宽（毫米）。 */
  width: number
  /** 高（毫米）。 */
  height: number
}

/** 内置纸张尺寸（毫米，纵向）。 */
export const PAPER_SIZES: Readonly<Record<'A4' | 'A5', PaperSize>> = {
  A4: { width: 210, height: 297 },
  A5: { width: 148, height: 210 },
}

/** 字段缺失占位文本（与格式化占位一致）。 */
export const PRINT_MISSING_TEXT = EMPTY_PLACEHOLDER

/** 打印样式变量名（变量值由宿主打印令牌组注入；核心只给名，不给值）。 */
export const PRINT_STYLE_VARS = {
  paper: '--bms-print-paper-bg',
  text: '--bms-print-text',
  margin: '--bms-print-margin',
  fontSize: '--bms-print-font-size',
  lineHeight: '--bms-print-line-height',
  lineWidth: '--bms-print-line-width',
  watermark: '--bms-print-watermark-color',
  monoFilter: '--bms-print-mono-filter',
} as const

/** 打印样式变量名类型。 */
export type PrintStyleVar = (typeof PRINT_STYLE_VARS)[keyof typeof PRINT_STYLE_VARS]

/** 单元格格式。 */
export type PrintCellFormat = 'text' | 'amount' | 'number' | 'date' | 'datetime'

/** 打印字段（字段区一项）。 */
export interface PrintFieldDef {
  /** 字段键（取 `data.fields` 同名值）。 */
  key: string
  /** 字段名（渲染在值之前）。 */
  label: string
  /** 内联值（优先于 `data.fields`，用于单据外补充信息）。 */
  value?: unknown
  /** 跨列数（缺省 1 列）。 */
  span?: number
  /** 值格式（缺省文本）。 */
  format?: PrintCellFormat
}

/** 明细列。 */
export interface PrintColumnDef {
  /** 列键（取行内同名值）。 */
  key: string
  /** 列名（每页表头重复渲染）。 */
  label: string
  /** 列宽（毫米或像素，由件层解释）。 */
  width?: number
  /** 对齐。 */
  align?: 'left' | 'center' | 'right'
  /** 值格式（缺省文本）。 */
  format?: PrintCellFormat
}

/** 明细行。 */
export type PrintRowData = Record<string, unknown>

/** 打印模板定义。 */
export interface PrintTemplateDef {
  /** 模板键（集合内唯一）。 */
  key: string
  /** 标题（如「销售订单」）。 */
  title: string
  /** 页眉副信息（如单据编号）。 */
  subtitle?: string
  /** 字段区（键值对；按列分行）。 */
  fields?: PrintFieldDef[]
  /** 明细列。 */
  columns?: PrintColumnDef[]
  /** 签章区标签（如制单 / 审核 / 客户签收）。 */
  signLabels?: string[]
  /** 页脚备注（附加在页码与打印信息之后）。 */
  footerNote?: string
  /** 汇总取值列键（页脚上方合计）。 */
  summaryKey?: string
  /** 汇总文案前缀（缺省「合计」）。 */
  summaryLabel?: string
  /** 每页明细行容量（非正或缺省时按纸张与行高计算）。 */
  rowsPerPage?: number
  /** 明细行高（毫米，用于容量计算）。 */
  rowHeight?: number
  /** 纸面固定占位高度（页眉 / 标题 / 字段 / 表头 / 签章 / 页脚合计，毫米）。 */
  chromeHeight?: number
}

/** 单据数据（主表字段 + 明细）。 */
export interface PrintData {
  /** 主表字段值（按字段键取值）。 */
  fields?: Record<string, unknown>
  /** 明细行。 */
  rows?: PrintRowData[]
}

/** 打印页（预分页结果；表头由件层在每页重复渲染）。 */
export interface PrintPage {
  /** 页码（1 起）。 */
  index: number
  /** 总页数。 */
  total: number
  /** 本页明细行。 */
  rows: PrintRowData[]
  /** 是否首页。 */
  isFirst: boolean
  /** 是否末页。 */
  isLast: boolean
  /** 页脚文案（页码 / 打印时间 / 打印人 / 备注）。 */
  footer: string
}

/** 分页输入。 */
export interface BuildPagesInput {
  /** 模板定义。 */
  template: PrintTemplateDef
  /** 单据数据。 */
  data?: PrintData
  /** 纸张尺寸（毫米，已按方向换算）。 */
  paperSize: PaperSize
  /** 打印时间（已格式化文本）。 */
  printedAt?: string
  /** 打印人。 */
  printedBy?: string
}

/** 行容量计算输入。 */
export interface RowCapacityInput {
  /** 纸张高（毫米）。 */
  paperHeight: number
  /** 明细行高（毫米）。 */
  rowHeight: number
  /** 纸面固定占位高度（毫米）。 */
  chromeHeight: number
}

/** 页脚输入。 */
export interface PageFooterInput {
  /** 页码（1 起）。 */
  index: number
  /** 总页数。 */
  total: number
  /** 打印时间。 */
  printedAt?: string
  /** 打印人。 */
  printedBy?: string
  /** 附加备注。 */
  note?: string
}

/** 色调解析结果。 */
export interface PrintToneResolve {
  /** 是否黑白。 */
  mono: boolean
  /** 置灰滤镜值（彩色时为空串）。 */
  filter: string
}

/** 缺省明细行高（毫米）。 */
const DEFAULT_ROW_HEIGHT = 8

/** 缺省纸面固定占位高度（毫米：页眉 / 标题 / 字段 / 表头 / 签章 / 页脚合计）。 */
const DEFAULT_CHROME_HEIGHT = 60

/**
 * 判断纸张尺寸是否合法（宽高均为正数）。
 *
 * @param size 纸张尺寸。
 */
function isValidSize(size: PaperSize | undefined): size is PaperSize {
  return (
    size !== undefined &&
    Number.isFinite(size.width) &&
    Number.isFinite(size.height) &&
    size.width > 0 &&
    size.height > 0
  )
}

/**
 * 解析纸张尺寸（横向交换宽高；`custom` 缺失或非法回落 A4）。
 *
 * @param paper 纸张名。
 * @param orientation 纸张方向（缺省纵向）。
 * @param custom 自定义尺寸（`custom` 时使用）。
 * @returns 纸张尺寸（毫米）。
 */
export function resolvePaperSize(
  paper: PaperName,
  orientation: PaperOrientation = 'portrait',
  custom?: PaperSize,
): PaperSize {
  const base = paper === 'custom' ? (isValidSize(custom) ? custom : PAPER_SIZES.A4) : PAPER_SIZES[paper]
  return orientation === 'landscape' ? { width: base.height, height: base.width } : { ...base }
}

/**
 * 计算每页明细行容量（至少 1 行；行高非正按 1 毫米处理）。
 *
 * @param input 行容量计算输入。
 * @returns 每页可容纳的明细行数。
 */
export function computeRowsPerPage(input: RowCapacityInput): number {
  const rowHeight = Number.isFinite(input.rowHeight) && input.rowHeight > 0 ? input.rowHeight : 1
  const paperHeight = Number.isFinite(input.paperHeight) ? input.paperHeight : 0
  const chromeHeight = Number.isFinite(input.chromeHeight) ? input.chromeHeight : 0
  return Math.max(1, Math.floor((paperHeight - chromeHeight) / rowHeight))
}

/**
 * 分页（保序；容量非正按 1 处理）。
 *
 * @param rows 待分页数据。
 * @param size 每页容量。
 * @returns 每页数据（空输入返回空数组）。
 */
export function paginateRows<T>(rows: readonly T[], size: number): T[][] {
  const capacity = Number.isFinite(size) && size > 0 ? Math.floor(size) : 1
  const pages: T[][] = []
  for (let index = 0; index < rows.length; index += capacity) {
    pages.push(rows.slice(index, index + capacity))
  }
  return pages
}

/**
 * 字段区按列数分行（保持原顺序）。
 *
 * @param fields 字段列表。
 * @param columns 列数（缺省 2 列）。
 * @returns 每行字段（不足一行留短行，件层渲染空位）。
 */
export function distributeFields<T>(fields: readonly T[], columns = 2): T[][] {
  return paginateRows(fields, Number.isFinite(columns) && columns > 0 ? Math.floor(columns) : 1)
}

/**
 * 数值列汇总（仅累加有限数值，其余跳过）。
 *
 * @param rows 明细行。
 * @param key 取值列键。
 * @returns 合计值（无有效值为 0）。
 */
export function sumNumeric(rows: readonly PrintRowData[], key: string): number {
  let total = 0
  for (const row of rows) {
    const value = row[key]
    if (value === undefined || value === null || value === '') {
      continue
    }
    const num = typeof value === 'number' ? value : Number(value)
    if (Number.isFinite(num)) {
      total += num
    }
  }
  return total
}

/**
 * 页脚文案（页码 / 打印时间 / 打印人 / 备注；缺失项不输出）。
 *
 * @param input 页脚输入。
 * @returns 页脚文本。
 */
export function formatPageFooter(input: PageFooterInput): string {
  const parts = [`第 ${Math.max(1, input.index)} 页 / 共 ${Math.max(1, input.total)} 页`]
  if (input.printedAt !== undefined && input.printedAt !== '') {
    parts.push(`打印时间 ${input.printedAt}`)
  }
  if (input.printedBy !== undefined && input.printedBy !== '') {
    parts.push(`打印人 ${input.printedBy}`)
  }
  if (input.note !== undefined && input.note !== '') {
    parts.push(input.note)
  }
  return parts.join(' · ')
}

/**
 * 打印色调解析（黑白置灰）。
 *
 * @param tone 打印色调。
 * @returns 是否黑白与置灰滤镜值（彩色为空串）。
 */
export function resolvePrintTone(tone: PrintTone): PrintToneResolve {
  return tone === 'mono' ? { mono: true, filter: 'grayscale(1)' } : { mono: false, filter: '' }
}

/**
 * 解析模板每页明细行容量（模板级声明优先，其次按纸张高、行高与占位高度计算）。
 *
 * @param template 模板定义。
 * @param paperSize 纸张尺寸（毫米）。
 * @returns 每页明细行数（至少 1）。
 */
export function resolveRowsPerPage(template: PrintTemplateDef, paperSize: PaperSize): number {
  const declared = template.rowsPerPage
  if (declared !== undefined && Number.isFinite(declared) && declared > 0) {
    return Math.floor(declared)
  }
  return computeRowsPerPage({
    paperHeight: paperSize.height,
    rowHeight: template.rowHeight ?? DEFAULT_ROW_HEIGHT,
    chromeHeight: template.chromeHeight ?? DEFAULT_CHROME_HEIGHT,
  })
}

/**
 * 构建打印页（模板级行容量优先；空明细返回单页空页，供空数据打印）。
 *
 * @param input 分页输入。
 * @returns 页数组（页码连续、首页 / 末页标记就位）。
 */
export function buildPrintPages(input: BuildPagesInput): PrintPage[] {
  const template = input.template
  const rows = input.data?.rows ?? []
  const capacity = resolveRowsPerPage(template, input.paperSize)
  const chunks = paginateRows(rows, capacity)
  const pageRows = chunks.length > 0 ? chunks : [[]]
  const total = pageRows.length
  return pageRows.map((currentRows, index) => ({
    index: index + 1,
    total,
    rows: currentRows,
    isFirst: index === 0,
    isLast: index === total - 1,
    footer: formatPageFooter({
      index: index + 1,
      total,
      printedAt: input.printedAt,
      printedBy: input.printedBy,
      note: template.footerNote,
    }),
  }))
}

/**
 * 单元格渲染文本（按格式走格式化；空值与非法值回落占位）。
 *
 * @param value 原值。
 * @param format 值格式（缺省文本）。
 * @param context 格式化上下文（语言 / 时区）。
 * @returns 渲染文本。
 */
export function formatCellValue(value: unknown, format: PrintCellFormat = 'text', context: FormatContext = {}): string {
  if (value === undefined || value === null || value === '') {
    return PRINT_MISSING_TEXT
  }
  switch (format) {
    case 'amount': {
      const num = Number(value)
      return Number.isFinite(num) ? formatAmount(num, context) : String(value)
    }
    case 'number': {
      const num = Number(value)
      return Number.isFinite(num) ? formatNumber(num, context) : String(value)
    }
    case 'date':
      return formatDate(value as string | number | Date, context)
    case 'datetime':
      return formatDateTime(value as string | number | Date, context)
    default:
      return String(value)
  }
}
