/**
 * 领域纯函数：导入（文件校验 / 内容派生幂等键 / 结果归一 / 错误行分页 / 文件级错误判定 / 下载文件名）。
 *
 * Excel 解析、模板列核对与行级校验归后端；本模块只做前端交互所需的纯数据推导，不触 DOM、不请求。
 */

import { formatCompactTimestamp } from './format'
import { fnv1aHex } from './serialize'

/** 导入执行权限码。 */
export const IMPORT_PERM = 'import:execute'
/** 接受的文件类型（白名单，逗号分隔）。 */
export const IMPORT_ACCEPT = '.xlsx'
/** 文件大小上限缺省值（字节；0 表示不限，`sys_config` 可配）。 */
export const IMPORT_DEFAULT_MAX_SIZE = 20 * 1024 * 1024
/** 错误行分页缺省每页行数。 */
export const IMPORT_ERROR_PAGE_SIZE = 20
/** 错误行展示上限（超限仅展示前 N 行并引导下载完整明细）。 */
export const IMPORT_ERROR_DISPLAY_LIMIT = 1000
/** 占位文案（数据通路未就绪）。 */
export const IMPORT_PLACEHOLDER_TEXT = '导入未就绪（占位）'
/** 文件段错误码区间（5xxxx，用于文件级错误判定）。 */
export const IMPORT_FILE_ERROR_RANGE: readonly [number, number] = [50001, 59999]

/** 文件校验失败原因。 */
export type ImportFailReason = 'type' | 'size' | 'empty'
/** 文件元信息（校验与幂等键输入；件层由 `File` 映射）。 */
export interface ImportFileMeta {
  /** 文件名（含扩展名）。 */
  name: string
  /** 字节大小。 */
  size: number
  /** 最后修改时间戳（毫秒）。 */
  lastModified?: number
}
/** 文件校验结果。 */
export interface ImportFileCheck {
  /** 是否通过。 */
  valid: boolean
  /** 失败原因（仅不通过时给出）。 */
  reason?: ImportFailReason
  /** 提示文案（通过时为空串）。 */
  message: string
}
/** 错误行（`row` 为 Excel 行号，自 2 起）。 */
export interface ImportErrorRow {
  /** 行号。 */
  row: number
  /** 出错列 / 字段（可选）。 */
  column?: string
  /** 原因文案（语言由后端返回或前端按 i18n 映射）。 */
  message: string
}
/** 导入结果（运行态确定值）。 */
export interface ImportResult {
  /** 总行数。 */
  total: number
  /** 成功行数。 */
  successCount: number
  /** 失败行数。 */
  failCount: number
  /** 错误行明细。 */
  errors: ImportErrorRow[]
}
/** 导入结果装载输入（后端可省略字段）。 */
export interface ImportResultInput {
  /** 总行数。 */
  total?: number
  /** 成功行数。 */
  successCount?: number
  /** 失败行数。 */
  failCount?: number
  /** 错误行（字段可省略）。 */
  errors?: readonly { row?: number; column?: string; message?: string }[]
}
/** 结果汇总态（空数据 / 全部成功 / 部分失败）。 */
export type ImportSummaryState = 'empty' | 'success' | 'warning'
/** 错误行分页结果。 */
export interface ImportErrorPage {
  /** 当前页码（夹取到有效范围）。 */
  page: number
  /** 总页数（至少 1）。 */
  pageCount: number
  /** 错误行总数（含截断部分）。 */
  total: number
  /** 本页错误行。 */
  rows: ImportErrorRow[]
  /** 是否触发展示上限截断（引导下载完整明细）。 */
  truncated: boolean
}
/** 错误文案（i18n 键 + 兜底文本）。 */
export interface ImportErrorText {
  /** i18n 键（`error.{code}`；无错误码时为空串）。 */
  i18nKey: string
  /** 兜底文本（后端返回的原因）。 */
  text: string
}

/**
 * 归一为整数计数（非法 / 缺省回落 0）。
 *
 * @param value 原始值。
 * @returns 非负整数。
 */
function toCount(value: number | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.floor(value) : 0
}

/**
 * 取文件扩展名（含点，小写）。
 *
 * @param name 文件名。
 * @returns 扩展名（无扩展名返回空串）。
 */
export function fileExtension(name: string): string {
  const index = name.lastIndexOf('.')
  return index < 0 ? '' : name.slice(index).toLowerCase()
}

/**
 * 归一接受的文件类型列表（拆分 / 小写 / 去空白 / 去重）。
 *
 * @param accept 逗号分隔的类型串。
 * @returns 归一后的类型列表（空串视为不限）。
 */
export function normalizeAccept(accept: string): string[] {
  return [
    ...new Set(
      accept
        .split(',')
        .map((item) => item.trim().toLowerCase())
        .filter((item) => item !== ''),
    ),
  ]
}

/**
 * 校验导入文件（类型 → 大小 → 空文件，顺序短路）。
 *
 * @param meta 文件元信息。
 * @param options 接受类型与大小上限（缺省用领域常量）。
 * @returns 校验结果。
 */
export function checkImportFile(
  meta: ImportFileMeta,
  options: { accept?: string; maxSize?: number } = {},
): ImportFileCheck {
  const accept = normalizeAccept(options.accept ?? IMPORT_ACCEPT)
  const maxSize = options.maxSize ?? IMPORT_DEFAULT_MAX_SIZE
  const extension = fileExtension(meta.name)
  if (accept.length > 0 && !accept.includes(extension)) {
    return { valid: false, reason: 'type', message: `仅支持 ${accept.join(' / ')} 文件` }
  }
  if (maxSize > 0 && meta.size > maxSize) {
    return { valid: false, reason: 'size', message: `文件大小超过 ${Math.max(1, Math.round(maxSize / 1024 / 1024))}MB` }
  }
  if (meta.size <= 0) {
    return { valid: false, reason: 'empty', message: '文件为空，请重新选择' }
  }
  return { valid: true, message: '' }
}

/**
 * 派生导入幂等键（内容派生：同内容同键、内容变更换键）。
 *
 * @param biz 业务标识（后端路径段）。
 * @param meta 文件元信息。
 * @returns 幂等键（`Idempotency-Key` 头取值）。
 */
export function deriveImportKey(biz: string, meta: ImportFileMeta): string {
  return `imp:${biz}:${fnv1aHex(`${biz}|${meta.name}|${meta.size}|${meta.lastModified ?? 0}`)}`
}

/**
 * 归一导入结果（省略字段补零 / 空数组，运行态一律确定值）。
 *
 * @param input 后端返回结果（可省略字段）。
 * @returns 归一后的结果。
 */
export function normalizeImportResult(input: ImportResultInput | undefined): ImportResult {
  const rawErrors = input?.errors ?? []
  const errors: ImportErrorRow[] = rawErrors.map((item) => {
    const column = item.column
    return column === undefined || column === ''
      ? { row: toCount(item.row), message: item.message ?? '' }
      : { row: toCount(item.row), column, message: item.message ?? '' }
  })
  const failCount = input?.failCount === undefined ? errors.length : toCount(input.failCount)
  return {
    total: toCount(input?.total),
    successCount: toCount(input?.successCount),
    failCount,
    errors,
  }
}

/**
 * 解析导入结果汇总态。
 *
 * @param result 归一后的结果。
 * @returns 汇总态。
 */
export function resolveImportSummary(result: ImportResult): ImportSummaryState {
  if (result.total <= 0) {
    return 'empty'
  }
  return result.failCount > 0 ? 'warning' : 'success'
}

/**
 * 是否文件级错误（错误码落在文件段；文件级错误整体拒绝、不展示错误行表）。
 *
 * 行级校验失败不走异常、随结果对象的 `errors` 返回，因此抛出的错误视为文件 / 网络级。
 *
 * @param code 错误码。
 * @returns 是否文件级错误。
 */
export function isFileLevelError(code: number | undefined): boolean {
  if (code === undefined || !Number.isFinite(code)) {
    return false
  }
  return code >= IMPORT_FILE_ERROR_RANGE[0] && code <= IMPORT_FILE_ERROR_RANGE[1]
}

/**
 * 解析错误行文案（有错误码给 i18n 键，后端文案作兜底）。
 *
 * @param input 错误码与后端文案。
 * @returns i18n 键与兜底文本。
 */
export function resolveImportErrorText(input: { code?: number; message?: string }): ImportErrorText {
  const text = input.message ?? ''
  if (input.code === undefined || !Number.isFinite(input.code)) {
    return { i18nKey: '', text }
  }
  return { i18nKey: `error.${input.code}`, text }
}

/**
 * 错误行分页（页码夹取；超展示上限仅取前 N 行并置截断标记）。
 *
 * @param rows 错误行。
 * @param page 目标页码。
 * @param pageSize 每页行数（缺省用领域常量）。
 * @returns 分页结果。
 */
export function paginateImportErrors(
  rows: readonly ImportErrorRow[],
  page: number,
  pageSize: number = IMPORT_ERROR_PAGE_SIZE,
): ImportErrorPage {
  const size = pageSize > 0 ? Math.floor(pageSize) : IMPORT_ERROR_PAGE_SIZE
  const total = rows.length
  const truncated = total > IMPORT_ERROR_DISPLAY_LIMIT
  const displayRows = truncated ? rows.slice(0, IMPORT_ERROR_DISPLAY_LIMIT) : [...rows]
  const pageCount = Math.max(1, Math.ceil(displayRows.length / size))
  const current = Math.min(Math.max(1, Math.floor(page) || 1), pageCount)
  const start = (current - 1) * size
  return { page: current, pageCount, total, rows: displayRows.slice(start, start + size), truncated }
}

/**
 * 导入模板文件名。
 *
 * @param bizName 业务中文名。
 * @returns 文件名。
 */
export function templateFileName(bizName: string): string {
  return `${bizName}-导入模板.xlsx`
}

/**
 * 导入错误明细文件名（含时间戳）。
 *
 * @param bizName 业务中文名。
 * @param at 时间。
 * @returns 文件名。
 */
export function errorReportFileName(bizName: string, at: Date | number): string {
  return `${bizName}-导入错误明细-${formatCompactTimestamp(at)}.xlsx`
}
