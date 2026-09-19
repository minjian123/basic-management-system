/**
 * 领域纯函数：国际化文案目录（语言清单归一与校验 / `msg_key` 命名轻校验 / 缺失派生 / 筛选 /
 * 变更集与脏基线 / 内容派生幂等键 / 分页与虚拟滚动判定 / 错误码文案 / 导出文件名）。
 *
 * 框架无关、无副作用、不发请求；装载输入（后端可省略字段）与运行态（确定值）分离。
 * 错误码口径见《概要设计 · 国际化管理》（44001 ~ 44005）。
 */

import { fnv1aHex, stableStringify } from './serialize'

/** 权限码（语言清单与语言包维护、缓存失效）。 */
export const I18N_PERM = 'i18n:manage'
/** 默认语言（不可停用）。 */
export const DEFAULT_LOCALE = 'zh-CN'
/** 单条文案值长度上限（Unicode 码点；与后端 `len()` 同口径，中文与 emoji 均按 1 计）。 */
export const MESSAGE_VALUE_MAX = 4000
/** 文案网格每页行数（缺省）。 */
export const MESSAGE_PAGE_SIZE = 50
/** 筛选态每页行数（宿主可加大；用于切虚拟滚动）。 */
export const MESSAGE_FILTER_PAGE_SIZE = 200
/** 超过该行数切换虚拟滚动。 */
export const MESSAGE_VIRTUAL_THRESHOLD = 200

/** 文案目录未就绪占位文案。 */
export const I18N_PLACEHOLDER_TEXT = '国际化文案未就绪（占位）'
/** 批量保存未就绪占位文案。 */
export const I18N_SAVE_PLACEHOLDER_TEXT = '批量保存未就绪（占位）'
/** 缓存失效未就绪占位文案。 */
export const I18N_CACHE_PLACEHOLDER_TEXT = '缓存失效未就绪（占位）'
/** 语言包重载未就绪占位文案。 */
export const I18N_RELOAD_PLACEHOLDER_TEXT = '语言包重载未就绪（占位）'
/** 无待保存变更提示。 */
export const I18N_NO_CHANGE_TEXT = '无待保存变更'
/** 文案值超长提示。 */
export const I18N_VALUE_TOO_LONG_TEXT = `文案值超长（最多 ${MESSAGE_VALUE_MAX} 字）`
/** 缺失标记文案。 */
export const I18N_MISSING_TEXT = '缺失'
/** 空数据文案。 */
export const I18N_EMPTY_TEXT = '暂无文案数据'
/** 保存成功文案。 */
export const I18N_SAVE_DONE_TEXT = '保存成功，文案已即时生效'
/** 保存成功但缓存失效失败的降级文案。 */
export const I18N_SAVE_WARNING_TEXT = '保存成功，但语言包缓存失效未完成（将按短 TTL 兜底）'
/** 缓存失效失败文案。 */
export const I18N_CACHE_FAILED_TEXT = '语言包缓存失效失败（将按短 TTL 兜底）'
/** 语言包重载失败文案。 */
export const I18N_RELOAD_FAILED_TEXT = '语言包重载失败，将在下次拉取时更新'
/** 文案键重复提示。 */
export const I18N_DUPLICATE_KEY_TEXT = '文案键已存在'

/** 语言包导出文件名前缀。 */
export const I18N_EXPORT_PREFIX = '语言包'

/** 语言状态。 */
export type I18nLocaleStatus = 'enabled' | 'disabled'

/** 语言清单项（运行态：字段确定）。 */
export interface I18nLocaleItem {
  /** 语言标识（如 `zh-CN`）。 */
  code: string
  /** 语言名。 */
  name: string
  /** 是否从右到左。 */
  rtl: boolean
  /** 状态。 */
  status: I18nLocaleStatus
}

/** 语言清单装载输入（后端可省略字段）。 */
export interface I18nLocaleInput {
  /** 语言标识。 */
  code: string
  /** 语言名（缺省取 code）。 */
  name?: string
  /** 是否从右到左（缺省 false）。 */
  rtl?: boolean
  /** 状态（缺省 `enabled`）。 */
  status?: I18nLocaleStatus
}

/** 文案行（运行态：`values` 覆盖全部语言键）。 */
export interface I18nMessageItem {
  /** 文案键。 */
  key: string
  /** 各语言值。 */
  values: Record<string, string>
  /** 缺失翻译的语言标识（前端派生与后端标记的并集）。 */
  missing: string[]
}

/** 文案行装载输入。 */
export interface I18nMessageInput {
  /** 文案键。 */
  key: string
  /** 各语言值。 */
  values?: Record<string, string>
  /** 后端标记的缺失语言。 */
  missing?: readonly string[]
}

/** 筛选条件。 */
export interface I18nFilter {
  /** 模块前缀（如 `user.form.`）。 */
  prefix: string
  /** 关键词（匹配 `msg_key` 或任一语言值）。 */
  keyword: string
  /** 只看存在缺失翻译的行。 */
  missingOnly: boolean
  /** 只看本次会话已修改的行。 */
  modifiedOnly: boolean
  /** 语言聚焦（非空时其他语言列隐藏 / 置灰）。 */
  locale: string
}

/** 空筛选条件。 */
export const EMPTY_I18N_FILTER: I18nFilter = {
  prefix: '',
  keyword: '',
  missingOnly: false,
  modifiedOnly: false,
  locale: '',
}

/** 分页视图。 */
export interface MessagePage<T> {
  /** 当前页数据。 */
  rows: T[]
  /** 当前页码（夹取后）。 */
  page: number
  /** 总页数（至少 1）。 */
  pageCount: number
  /** 总条数。 */
  total: number
  /** 是否被分页截断（总页数大于 1）。 */
  truncated: boolean
}

/** 保存变更集（内容派生幂等键的输入）。 */
export interface I18nChangeSet {
  /** 新增或更新的行（按 key 升序）。 */
  upserts: { key: string; values: Record<string, string> }[]
  /** 删除的 key（升序）。 */
  removedKeys: string[]
  /** 语言清单（运行态，按 code 升序）。 */
  locales: I18nLocaleItem[]
}

/** 校验结果（错误码 + 文案）。 */
export interface I18nCheckResult {
  /** 是否通过。 */
  valid: boolean
  /** 错误码（通过时为 0）。 */
  code: number
  /** 文案。 */
  message: string
}

/** 国际化模块错误码（《概要设计 · 国际化管理》）。 */
export const I18N_ERRORS = {
  /** 语言 code 已存在。 */
  DUPLICATE_LOCALE: 44001,
  /** 语言存在关联语言包数据，不可删除。 */
  LOCALE_IN_USE: 44002,
  /** `msg_key` 格式非法。 */
  INVALID_KEY: 44003,
  /** 至少保留一种启用的语言。 */
  LAST_LOCALE: 44004,
  /** 默认语言不可停用。 */
  DEFAULT_LOCALE: 44005,
} as const

/** 错误码文案表。 */
const ERROR_TEXTS: Readonly<Record<number, string>> = {
  [I18N_ERRORS.DUPLICATE_LOCALE]: '语言标识已存在',
  [I18N_ERRORS.LOCALE_IN_USE]: '该语言存在语言包数据，仅可停用',
  [I18N_ERRORS.INVALID_KEY]: '文案键须符合「模块.页面.字段」命名',
  [I18N_ERRORS.LAST_LOCALE]: '至少保留一种启用的语言',
  [I18N_ERRORS.DEFAULT_LOCALE]: '默认语言不可停用',
}

/** 通过结果。 */
const OK: I18nCheckResult = { valid: true, code: 0, message: '' }

/**
 * 构造失败结果。
 *
 * @param code 错误码。
 * @param message 文案（缺省取错误码表）。
 */
function fail(code: number, message?: string): I18nCheckResult {
  return { valid: false, code, message: message ?? ERROR_TEXTS[code] ?? `错误码 ${code}` }
}

/**
 * 归一语言标识（去空白）。
 *
 * @param code 语言标识。
 */
function normalizeCode(code: string): string {
  return String(code ?? '').trim()
}

/**
 * 归一语言清单项（装载输入 → 运行态确定值）。
 *
 * @param input 装载输入。
 * @returns 运行态语言项。
 */
export function normalizeLocale(input: I18nLocaleInput): I18nLocaleItem {
  const code = normalizeCode(input.code)
  return {
    code,
    name: input.name === undefined || String(input.name).trim() === '' ? code : String(input.name).trim(),
    rtl: input.rtl ?? false,
    status: input.status ?? 'enabled',
  }
}

/**
 * 归一语言清单（逐项归一）。
 *
 * @param input 装载输入清单。
 * @returns 运行态语言项清单。
 */
export function normalizeLocales(input: readonly I18nLocaleInput[]): I18nLocaleItem[] {
  return input.map((item) => normalizeLocale(item))
}

/**
 * 取语言列集（停用语言是否含入由 `includeDisabled` 决定）。
 *
 * @param locales 语言清单。
 * @param includeDisabled 是否含停用语言（缺省 false）。
 * @returns 列集。
 */
export function localeColumns(locales: readonly I18nLocaleItem[], includeDisabled = false): I18nLocaleItem[] {
  return includeDisabled ? [...locales] : locales.filter((item) => item.status === 'enabled')
}

/**
 * 校验新增语言（`code` 非空且唯一，44001）。
 *
 * @param input 新增输入。
 * @param locales 现有语言清单。
 * @returns 校验结果。
 */
export function validateLocaleAdd(input: I18nLocaleInput, locales: readonly I18nLocaleItem[]): I18nCheckResult {
  const code = normalizeCode(input.code)
  if (code === '') {
    return fail(I18N_ERRORS.DUPLICATE_LOCALE, '语言标识不可为空')
  }
  const exists = locales.some((item) => item.code.toLowerCase() === code.toLowerCase())
  return exists ? fail(I18N_ERRORS.DUPLICATE_LOCALE) : OK
}

/**
 * 校验语言启停（默认语言不可停用 44005；至少保留一种启用语言 44004）。
 *
 * @param code 语言标识。
 * @param enabled 目标状态。
 * @param locales 现有语言清单。
 * @param defaultLocale 默认语言（缺省 `zh-CN`）。
 * @returns 校验结果。
 */
export function validateLocaleToggle(
  code: string,
  enabled: boolean,
  locales: readonly I18nLocaleItem[],
  defaultLocale: string = DEFAULT_LOCALE,
): I18nCheckResult {
  const target = normalizeCode(code)
  if (enabled) {
    return OK
  }
  if (target === defaultLocale) {
    return fail(I18N_ERRORS.DEFAULT_LOCALE)
  }
  const remaining = locales.filter((item) => item.code !== target && item.status === 'enabled')
  return remaining.length === 0 ? fail(I18N_ERRORS.LAST_LOCALE) : OK
}

/**
 * 校验语言修改（目标存在性 + 启停规则）。
 *
 * @param code 原语言标识。
 * @param patch 修改内容。
 * @param locales 现有语言清单。
 * @param defaultLocale 默认语言。
 * @returns 校验结果。
 */
export function validateLocaleUpdate(
  code: string,
  patch: I18nLocaleInput,
  locales: readonly I18nLocaleItem[],
  defaultLocale: string = DEFAULT_LOCALE,
): I18nCheckResult {
  const target = normalizeCode(code)
  if (!locales.some((item) => item.code === target)) {
    return fail(I18N_ERRORS.DUPLICATE_LOCALE, '语言不存在')
  }
  if (patch.status === undefined || patch.status === 'enabled') {
    return OK
  }
  return validateLocaleToggle(target, false, locales, defaultLocale)
}

/**
 * 校验语言删除（有语言包数据不可删 44002；默认语言保护 44005；至少保留一种 44004）。
 *
 * @param code 语言标识。
 * @param locales 现有语言清单。
 * @param hasMessages 该语言是否已有语言包数据。
 * @param defaultLocale 默认语言。
 * @returns 校验结果。
 */
export function validateLocaleRemove(
  code: string,
  locales: readonly I18nLocaleItem[],
  hasMessages: boolean,
  defaultLocale: string = DEFAULT_LOCALE,
): I18nCheckResult {
  const target = normalizeCode(code)
  if (hasMessages) {
    return fail(I18N_ERRORS.LOCALE_IN_USE)
  }
  if (target === defaultLocale) {
    return fail(I18N_ERRORS.DEFAULT_LOCALE, '默认语言不可删除')
  }
  return locales.length <= 1 ? fail(I18N_ERRORS.LAST_LOCALE) : OK
}

/**
 * 归一文案键（去空白）。
 *
 * @param key 文案键。
 */
export function normalizeMessageKey(key: string): string {
  return String(key ?? '').trim()
}

/**
 * 校验文案键命名（`模块.页面.字段`：至少 2 段、每段非空且不含空白，44003）。
 *
 * @param key 文案键。
 * @returns 校验结果。
 */
export function validateMessageKey(key: string): I18nCheckResult {
  const target = normalizeMessageKey(key)
  if (target === '') {
    return fail(I18N_ERRORS.INVALID_KEY)
  }
  const segments = target.split('.')
  const valid = segments.length >= 2 && segments.every((segment) => segment !== '' && !/\s/.test(segment))
  return valid ? OK : fail(I18N_ERRORS.INVALID_KEY)
}

/**
 * 校验文案值长度（空值不算超长；按 **Unicode 码点**计，中文与 emoji 均按 1 计）。
 *
 * @param value 文案值。
 * @returns 校验结果。
 */
export function validateMessageValue(value: string): I18nCheckResult {
  return Array.from(String(value ?? '')).length > MESSAGE_VALUE_MAX
    ? fail(0, I18N_VALUE_TOO_LONG_TEXT)
    : OK
}

/**
 * 派生缺失语言（前端派生「去空白为空」与后端标记取并集，按语言清单顺序）。
 *
 * @param values 各语言值。
 * @param locales 语言清单。
 * @param declared 后端标记的缺失语言。
 * @returns 缺失语言标识（去重、按清单顺序）。
 */
export function deriveMissingLocales(
  values: Readonly<Record<string, string>>,
  locales: readonly I18nLocaleItem[],
  declared: readonly string[] = [],
): string[] {
  const set = new Set(declared.map((code) => normalizeCode(code)).filter((code) => code !== ''))
  for (const item of locales) {
    if (String(values[item.code] ?? '').trim() === '') {
      set.add(item.code)
    }
  }
  return locales.filter((item) => set.has(item.code)).map((item) => item.code)
}

/**
 * 归一文案行（`values` 补齐语言键、去空白、非字符串回落空串；`missing` 按**启用语言**归一）。
 *
 * 缺失只按启用语言判定（停用语言不需补齐），`values` 仍保留全部语言键以承载存量值。
 *
 * @param input 装载输入。
 * @param locales 语言清单（缺省空：仅保留入参已有键）。
 * @returns 运行态文案行。
 */
export function normalizeMessage(
  input: I18nMessageInput,
  locales: readonly I18nLocaleItem[] = [],
): I18nMessageItem {
  const source = input.values ?? {}
  const values: Record<string, string> = {}
  const codes = locales.length > 0 ? locales.map((item) => item.code) : Object.keys(source)
  for (const code of codes) {
    const value = source[code]
    values[code] = value === undefined || value === null ? '' : String(value)
  }
  const enabled = localeColumns(locales)
  const declared = enabled.length > 0 ? (input.missing ?? []).filter((code) => enabled.some((item) => item.code === code)) : (input.missing ?? [])
  return {
    key: normalizeMessageKey(input.key),
    values,
    missing: deriveMissingLocales(values, enabled, declared),
  }
}

/**
 * 归一文案行集合。
 *
 * @param input 装载输入集合。
 * @param locales 语言清单。
 * @returns 运行态文案行集合。
 */
export function normalizeMessages(
  input: readonly I18nMessageInput[],
  locales: readonly I18nLocaleItem[] = [],
): I18nMessageItem[] {
  return input.map((item) => normalizeMessage(item, locales))
}

/**
 * 某行某语言是否缺失。
 *
 * @param row 文案行。
 * @param code 语言标识。
 */
export function isMessageMissing(row: I18nMessageItem, code: string): boolean {
  return row.missing.includes(code)
}

/**
 * 行是否被修改（基线无该行或值不同）。
 *
 * @param row 当前行。
 * @param baselineRow 基线行（缺省视为新增）。
 * @returns 是否修改。
 */
export function isModifiedRow(row: I18nMessageItem, baselineRow?: I18nMessageItem): boolean {
  if (baselineRow === undefined) {
    return true
  }
  return stableStringify(row.values) !== stableStringify(baselineRow.values)
}

/**
 * 按条件筛选文案行（缺失 / 语言聚焦 / 仅已修改为本地判定，不额外请求）。
 *
 * @param rows 文案行。
 * @param filter 筛选条件。
 * @param baseline 基线行（「仅已修改」判定用）。
 * @returns 命中行。
 */
export function filterMessages(
  rows: readonly I18nMessageItem[],
  filter: I18nFilter,
  baseline: readonly I18nMessageItem[] = [],
): I18nMessageItem[] {
  const prefix = filter.prefix.trim()
  const keyword = filter.keyword.trim().toLowerCase()
  const focus = filter.locale.trim()
  const baselineMap = new Map(baseline.map((row) => [row.key, row]))
  return rows.filter((row) => {
    if (prefix !== '' && !row.key.startsWith(prefix)) {
      return false
    }
    if (keyword !== '') {
      const hitKey = row.key.toLowerCase().includes(keyword)
      const hitValue = Object.values(row.values).some((value) => value.toLowerCase().includes(keyword))
      if (!hitKey && !hitValue) {
        return false
      }
    }
    if (filter.missingOnly && row.missing.length === 0) {
      return false
    }
    if (focus !== '' && !row.missing.includes(focus)) {
      return false
    }
    if (filter.modifiedOnly && !isModifiedRow(row, baselineMap.get(row.key))) {
      return false
    }
    return true
  })
}

/**
 * 装配下发后端的筛选参数（剔空；`modified` 为纯前端条件不下发）。
 *
 * @param filter 筛选条件。
 * @returns 查询参数。
 */
export function resolveFilterParams(filter: I18nFilter): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  if (filter.prefix.trim() !== '') {
    params.prefix = filter.prefix.trim()
  }
  if (filter.keyword.trim() !== '') {
    params.keyword = filter.keyword.trim()
  }
  if (filter.missingOnly) {
    params.missing = true
  }
  if (filter.locale.trim() !== '') {
    params.locale = filter.locale.trim()
  }
  return params
}

/**
 * 计算变更集（逐行比对；键序稳定）。
 *
 * @param baseline 基线行。
 * @param current 当前行。
 * @param locales 语言清单（运行态）。
 * @returns 变更集。
 */
export function diffMessages(
  baseline: readonly I18nMessageItem[],
  current: readonly I18nMessageItem[],
  locales: readonly I18nLocaleItem[] = [],
): I18nChangeSet {
  const baselineMap = new Map(baseline.map((row) => [row.key, row]))
  const currentKeys = new Set(current.map((row) => row.key))
  const upserts = current
    .filter((row) => isModifiedRow(row, baselineMap.get(row.key)))
    .map((row) => ({ key: row.key, values: { ...row.values } }))
    .sort((left, right) => (left.key < right.key ? -1 : 1))
  const removedKeys = baseline
    .map((row) => row.key)
    .filter((key) => !currentKeys.has(key))
    .sort((left, right) => (left < right ? -1 : 1))
  const localeItems = [...locales].sort((left, right) => (left.code < right.code ? -1 : 1))
  return { upserts, removedKeys, locales: localeItems.map((item) => ({ ...item })) }
}

/**
 * 是否存在未保存变更。
 *
 * @param baseline 基线行。
 * @param current 当前行。
 * @returns 是否脏。
 */
export function isDirty(baseline: readonly I18nMessageItem[], current: readonly I18nMessageItem[]): boolean {
  const changeSet = diffMessages(baseline, current)
  return changeSet.upserts.length > 0 || changeSet.removedKeys.length > 0
}

/**
 * 派生内容幂等键（同一变更集同键、改一处换键）。
 *
 * @param changeSet 变更集。
 * @returns 幂等键（`i18n:{hash}`）。
 */
export function deriveMessageKey(changeSet: I18nChangeSet): string {
  return `i18n:${fnv1aHex(stableStringify(changeSet))}`
}

/**
 * 本地分页（页码夹取；`truncated` 表示总页数大于 1）。
 *
 * @param rows 文案行。
 * @param page 目标页码。
 * @param size 每页行数（至少 1）。
 * @returns 分页视图。
 */
export function paginateMessages<T>(rows: readonly T[], page: number, size: number): MessagePage<T> {
  const total = rows.length
  const pageSize = Math.max(1, Math.floor(size) || 1)
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const current = Math.min(Math.max(1, Math.floor(page) || 1), pageCount)
  return {
    rows: rows.slice((current - 1) * pageSize, current * pageSize),
    page: current,
    pageCount,
    total,
    truncated: pageCount > 1,
  }
}

/**
 * 是否切换虚拟滚动（行数超阈值）。
 *
 * @param rowCount 行数。
 * @param threshold 阈值（缺省 `MESSAGE_VIRTUAL_THRESHOLD`）。
 * @returns 是否虚拟滚动。
 */
export function shouldVirtualize(rowCount: number, threshold: number = MESSAGE_VIRTUAL_THRESHOLD): boolean {
  return rowCount > Math.max(0, Math.floor(threshold))
}

/**
 * 错误码 → 文案（未知码回落 `error.{code}`）。
 *
 * @param code 错误码。
 * @returns 文案。
 */
export function resolveMessageErrorText(code: number): string {
  return ERROR_TEXTS[code] ?? `error.${code}`
}

/**
 * 语言包导出文件名（`语言包[-{locale}]-{yyyyMMddHHmmss}.xlsx`）。
 *
 * @param locale 聚焦语言（空串表示全语言）。
 * @param timestamp 时间戳。
 * @returns 文件名。
 */
export function messageExportFileName(locale: string, timestamp: Date): string {
  const stamp = [
    timestamp.getFullYear(),
    pad(timestamp.getMonth() + 1),
    pad(timestamp.getDate()),
    pad(timestamp.getHours()),
    pad(timestamp.getMinutes()),
    pad(timestamp.getSeconds()),
  ].join('')
  const scope = locale.trim()
  return `${I18N_EXPORT_PREFIX}${scope === '' ? '' : `-${scope}`}-${stamp}.xlsx`
}

/**
 * 两位补零。
 *
 * @param value 数值。
 */
function pad(value: number): string {
  return String(value).padStart(2, '0')
}
