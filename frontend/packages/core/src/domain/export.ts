/**
 * 领域纯函数：导出（取数参数归一 / 选中集合归一 / 通路判定 / 明文判定 / 决策 / 文件名 / 错误文案）。
 *
 * 导出与列表查询**同一取数口径**（关键字、字段条件、区间、多列排序直传）；导出列顺序遵循导出模板归后端。
 * 本模块只做前端交互所需的纯数据推导，不触 DOM、不请求。
 */

import { formatCompactTimestamp } from './format'

/** 导出动作权限码。 */
export const EXPORT_PERM = 'export:download'
/** 明文导出权限码。 */
export const EXPORT_PLAIN_PERM = 'data:plain'
/** 占位文案（数据通路未就绪）。 */
export const EXPORT_PLACEHOLDER_TEXT = '导出未就绪（占位）'
/** 无数据提示文案。 */
export const EXPORT_EMPTY_TEXT = '当前筛选无数据可导出'
/** 后台异步导出提示文案。 */
export const EXPORT_QUEUED_TEXT = '数据量较大，已转后台导出，完成后在通知中心查看下载'
/** 导出文件扩展名。 */
export const EXPORT_FILE_EXT = '.xlsx'

/** 导出范围（当前筛选结果 / 选中行）。 */
export type ExportScope = 'filtered' | 'selected'
/** 导出通路（同步文件流 / 后台任务）。 */
export type ExportMode = 'sync' | 'async'
/** 取数参数（与列表查询同口径）。 */
export type ExportQueryParams = Record<string, unknown>

/** 导出决策输入。 */
export interface ExportDecisionInput {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 外部禁用。 */
  disabled?: boolean
  /** 是否有导出权限。 */
  permAllowed?: boolean
  /** 导出范围。 */
  scope?: ExportScope
  /** 选中行标识。 */
  selectedIds?: readonly (string | number)[]
  /** 当前筛选总条数。 */
  total?: number
  /** 异步阈值（0 = 前端不判断）。 */
  threshold?: number
}

/** 导出决策（可否导出 + 通路）。 */
export interface ExportDecision {
  /** 是否可导出。 */
  allowed: boolean
  /** 不可导出原因（允许时缺省）。 */
  reason?: 'degraded' | 'disabled' | 'forbidden' | 'no-selection' | 'empty'
  /** 导出通路。 */
  mode: ExportMode
}

/**
 * 归一取数参数（剔除 `undefined` / `null` / 空串 / 空数组项，键名不改写）。
 *
 * @param params 原始取数参数。
 * @returns 归一后的参数。
 */
export function normalizeExportParams(params?: Record<string, unknown>): ExportQueryParams {
  const result: ExportQueryParams = {}
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null) {
      continue
    }
    if (typeof value === 'string' && value.trim() === '') {
      continue
    }
    if (Array.isArray(value) && value.length === 0) {
      continue
    }
    result[key] = value
  }
  return result
}

/**
 * 归一选中行标识（字符串化 + 去重 + 排序；空集合回落 `undefined`）。
 *
 * @param ids 选中行标识。
 * @returns 归一后的标识集合；未选中返回 `undefined`。
 */
export function normalizeSelectedIds(ids?: readonly (string | number)[]): string[] | undefined {
  if (ids === undefined || ids.length === 0) {
    return undefined
  }
  return [...new Set(ids.map((id) => String(id)))].sort()
}

/**
 * 解析导出通路（超过阈值转后台任务）。
 *
 * @param input 总条数与异步阈值（阈值 0 = 前端不判断）。
 * @returns 通路。
 */
export function resolveExportMode(input: { total?: number; threshold?: number }): ExportMode {
  const threshold = input.threshold ?? 0
  const total = input.total ?? 0
  return threshold > 0 && total > threshold ? 'async' : 'sync'
}

/**
 * 是否按明文导出（申请明文且持 `data:plain` 才为真）。
 *
 * @param plain 是否申请明文。
 * @param plainAllowed 是否持有明文权限码。
 * @returns 是否明文导出。
 */
export function canExportPlain(plain: boolean, plainAllowed: boolean): boolean {
  return plain && plainAllowed
}

/**
 * 解析导出决策（就绪 / 禁用 / 权限 / 选中 / 无数据，顺序判定）。
 *
 * @param input 决策输入。
 * @returns 决策结果。
 */
export function resolveExportDecision(input: ExportDecisionInput = {}): ExportDecision {
  const mode = resolveExportMode({ total: input.total, threshold: input.threshold })
  const scope = input.scope ?? 'filtered'
  if (input.ready === false) {
    return { allowed: false, reason: 'degraded', mode }
  }
  if (input.disabled === true) {
    return { allowed: false, reason: 'disabled', mode }
  }
  if (input.permAllowed === false) {
    return { allowed: false, reason: 'forbidden', mode }
  }
  if (scope === 'selected' && (input.selectedIds?.length ?? 0) === 0) {
    return { allowed: false, reason: 'no-selection', mode }
  }
  if ((input.total ?? 0) <= 0) {
    return { allowed: false, reason: 'empty', mode }
  }
  return { allowed: true, mode }
}

/**
 * 导出文件名（前缀 + 紧凑时间戳 + 扩展名）。
 *
 * @param prefix 文件名前缀（缺省由调用方取业务中文名 / 业务标识）。
 * @param at 导出时间。
 * @returns 文件名。
 */
export function exportFileName(prefix: string, at: Date | number): string {
  return `${prefix}-${formatCompactTimestamp(at)}${EXPORT_FILE_EXT}`
}

/**
 * 解析导出失败文案（无权限 / 限流与服务错误 / 兜底）。
 *
 * @param code 错误码（宿主请求层错误码）。
 * @param fallback 兜底文案（件层可传 i18n 文案）。
 * @returns 提示文案。
 */
export function exportErrorMessage(code: number | undefined, fallback = ''): string {
  if (code === 403) {
    return '无导出权限'
  }
  if (code !== undefined && Number.isFinite(code) && code >= 50000 && code <= 59999) {
    return fallback === '' ? '导出失败，请稍后重试' : fallback
  }
  return fallback
}
