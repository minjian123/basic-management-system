/**
 * 领域纯函数：全局搜索（域 / 命中归一、域权限过滤、查询参数、分组与 Top N、
 * 日志时间范围校验、最近搜索、降级与错误码）。
 *
 * 不触 DOM、不请求、不依赖渲染框架与第三方库；同输入同输出。
 * 命中字段与后端检索结果对齐（`docType` 兼容 `doc_type`、`bizId` 兼容 `biz_id`）；
 * 命中只含 ID + 高亮，详情一律回查数据库。
 */

/** 审计日志检索权限码。 */
export const SEARCH_LOG_PERM = 'log:query'

/** 文件内容检索权限码。 */
export const SEARCH_FILE_PERM = 'file:query'

/** 即时建议防抖（毫秒）。 */
export const SEARCH_SUGGEST_DEBOUNCE = 250

/** 即时建议总量上限。 */
export const SEARCH_SUGGEST_LIMIT = 8

/** 即时建议各域上限。 */
export const SEARCH_SUGGEST_PER_DOMAIN = 3

/** 结果页页长缺省。 */
export const SEARCH_PAGE_SIZE_DEFAULT = 20

/** 结果页页长上限。 */
export const SEARCH_PAGE_SIZE_MAX = 100

/** 结果页限深（≤ 100 页）。 */
export const SEARCH_PAGE_DEPTH_MAX = 100

/** 最近搜索上限。 */
export const SEARCH_RECENT_MAX = 8

/** 审计日志单次时间范围上限（天，与错误码 10107 同源）。 */
export const SEARCH_LOG_RANGE_MAX_DAYS = 31

/** 关键词长度上限（码点）。 */
export const SEARCH_KEYWORD_MAX = 200

/** 占位文案。 */
export const SEARCH_PLACEHOLDER_TEXT = '搜索服务未就绪（占位）'

/** 降级提示文案。 */
export const SEARCH_DEGRADE_TEXT = '检索服务降级，结果可能不完整'

/** 降级替代入口文案。 */
export const SEARCH_DEGRADE_FALLBACK_TEXT = '前往各域列表'

/** 空态文案。 */
export const SEARCH_EMPTY_TEXT = '未找到相关内容'

/** 审计时间范围必填提示。 */
export const SEARCH_LOG_RANGE_REQUIRED_TEXT = '请选择时间范围'

/** 审计时间范围超限提示。 */
export const SEARCH_LOG_RANGE_EXCEED_TEXT = '单次检索时间范围不得超过 31 天'

/** 文件不可检索提示。 */
export const SEARCH_FILE_UNSEARCHABLE_TEXT = '该文件不可检索'

/** 限流提示。 */
export const SEARCH_RATE_LIMIT_TEXT = '请求过于频繁，请稍后重试'

/** 已知检索域（`doc_type`，与后端索引域同源）。 */
export type SearchDocType = 'user' | 'dept' | 'role' | 'dict' | 'prd' | 'file_meta' | 'help_article' | 'log'

/** 已知检索域集合。 */
export const SEARCH_DOC_TYPES: readonly SearchDocType[] = [
  'user',
  'dept',
  'role',
  'dict',
  'prd',
  'file_meta',
  'help_article',
  'log',
]

/** 降级原因（不可用 / 超时 / 兜底）。 */
export type SearchDegradeReason = 'unavailable' | 'timeout' | 'fallback'

/** 降级原因集合。 */
export const SEARCH_DEGRADE_REASONS: readonly SearchDegradeReason[] = ['unavailable', 'timeout', 'fallback']

/** 检索阶段。 */
export type SearchPhase = 'idle' | 'loading' | 'ready' | 'empty' | 'error'

/** 可检索域（`perm` 为该域业务权限码，缺省表示无单独权限要求）。 */
export interface SearchDomain {
  /** 域标识（与 `doc_type` 同源）。 */
  key: string
  /** 域名称。 */
  label: string
  /** 域业务权限码（缺省不校验）。 */
  perm?: string
}

/** 命中项（只含 ID + 高亮，详情回查库）。 */
export interface SearchHit {
  /** 文档类型。 */
  docType: string
  /** 业务 ID。 */
  bizId: string
  /** 标题（可含高亮标签）。 */
  title: string
  /** 高亮片段（白名单清洗后渲染）。 */
  highlight?: string
  /** 更新时间。 */
  updatedAt?: string
  /** 是否不可检索（文件域 10106 标记）。 */
  unsearchable?: boolean
}

/** 分组结果。 */
export interface SearchGroup {
  /** 域标识。 */
  key: string
  /** 域名称。 */
  label: string
  /** 命中项。 */
  items: SearchHit[]
}

/** 聚合结果（含降级标记）。 */
export interface SearchResult {
  /** 分组结果。 */
  groups: SearchGroup[]
  /** 命中总数。 */
  total: number
  /** 是否降级（10103）。 */
  degraded?: boolean
  /** 降级原因。 */
  degradeReason?: SearchDegradeReason
}

/** 时间范围。 */
export interface SearchRange {
  /** 起点（ISO 字符串）。 */
  start?: string
  /** 终点（ISO 字符串）。 */
  end?: string
}

/** 全局搜索查询条件。 */
export interface SearchGlobalQuery {
  /** 关键词。 */
  keyword: string
  /** 限定域（空表示全部可检索域）。 */
  types?: readonly string[]
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 审计日志检索查询条件。 */
export interface SearchLogQuery {
  /** 关键词。 */
  keyword: string
  /** 日志类型（缺省不限定）。 */
  logType?: string
  /** 起点（必填）。 */
  start: string
  /** 终点（必填）。 */
  end: string
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 文件内容检索查询条件。 */
export interface SearchFileQuery {
  /** 关键词。 */
  keyword: string
  /** 文件类型（缺省不限定）。 */
  fileType?: string
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 校验结果。 */
export interface SearchValidation {
  /** 是否通过。 */
  valid: boolean
  /** 未通过提示。 */
  message?: string
}

/**
 * 归一字符串（去首尾空格，空串回落 `undefined`）。
 *
 * @param value 原始值。
 * @returns 字符串或 `undefined`。
 */
function normalizeText(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim() !== '') {
    return value.trim()
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return undefined
}

/**
 * 归一布尔（兼容 `true` / `1` / `'1'`）。
 *
 * @param value 原始值。
 * @returns 布尔值（无法识别返回 `undefined`）。
 */
function normalizeBool(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') {
    return value
  }
  if (value === 1 || value === '1' || value === 'true') {
    return true
  }
  if (value === 0 || value === '0' || value === 'false') {
    return false
  }
  return undefined
}

/**
 * 归一可检索域（`key` 缺失视为脏项）。
 *
 * @param value 原始域。
 * @returns 归一域或 `undefined`。
 */
export function normalizeSearchDomain(value: unknown): SearchDomain | undefined {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  const raw = value as Record<string, unknown>
  const key = normalizeText(raw.key)
  if (key === undefined) {
    return undefined
  }
  const domain: SearchDomain = { key, label: normalizeText(raw.label) ?? key }
  const perm = normalizeText(raw.perm)
  if (perm !== undefined) {
    domain.perm = perm
  }
  return domain
}

/**
 * 归一可检索域数组（脏项剔除）。
 *
 * @param value 原始数组。
 * @returns 归一域数组。
 */
export function normalizeSearchDomains(value: unknown): SearchDomain[] {
  if (!Array.isArray(value)) {
    return []
  }
  const out: SearchDomain[] = []
  for (const entry of value) {
    const domain = normalizeSearchDomain(entry)
    if (domain !== undefined) {
      out.push(domain)
    }
  }
  return out
}

/**
 * 归一单条命中（缺 `bizId` / `title` 视为脏项）。
 *
 * @param value 原始命中。
 * @returns 归一命中或 `undefined`。
 */
export function normalizeSearchHit(value: unknown): SearchHit | undefined {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  const raw = value as Record<string, unknown>
  const bizId = normalizeText(raw.bizId ?? raw.biz_id)
  const title = normalizeText(raw.title)
  if (bizId === undefined || title === undefined) {
    return undefined
  }
  const hit: SearchHit = {
    docType: normalizeText(raw.docType ?? raw.doc_type) ?? 'unknown',
    bizId,
    title,
  }
  const highlight = normalizeText(raw.highlight)
  if (highlight !== undefined) {
    hit.highlight = highlight
  }
  const updatedAt = normalizeText(raw.updatedAt ?? raw.updated_at)
  if (updatedAt !== undefined) {
    hit.updatedAt = updatedAt
  }
  const unsearchable = normalizeBool(raw.unsearchable ?? (raw.searchable === false ? true : undefined))
  if (unsearchable === true) {
    hit.unsearchable = true
  }
  return hit
}

/**
 * 归一命中数组（脏项剔除）。
 *
 * @param value 原始数组。
 * @returns 归一命中数组。
 */
export function normalizeSearchHits(value: unknown): SearchHit[] {
  if (!Array.isArray(value)) {
    return []
  }
  const out: SearchHit[] = []
  for (const entry of value) {
    const hit = normalizeSearchHit(entry)
    if (hit !== undefined) {
      out.push(hit)
    }
  }
  return out
}

/**
 * 归一单个分组（缺 `key` 视为脏组）。
 *
 * @param value 原始分组。
 * @returns 归一分组或 `undefined`。
 */
export function normalizeSearchGroup(value: unknown): SearchGroup | undefined {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  const raw = value as Record<string, unknown>
  const key = normalizeText(raw.key)
  if (key === undefined) {
    return undefined
  }
  return {
    key,
    label: normalizeText(raw.label) ?? key,
    items: normalizeSearchHits(raw.items),
  }
}

/**
 * 归一聚合结果（非对象 / 脏组回落空结果）。
 *
 * @param value 原始结果。
 * @returns 归一聚合结果。
 */
export function normalizeSearchResult(value: unknown): SearchResult {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return { groups: [], total: 0 }
  }
  const raw = value as Record<string, unknown>
  const groups: SearchGroup[] = []
  if (Array.isArray(raw.groups)) {
    for (const entry of raw.groups) {
      const group = normalizeSearchGroup(entry)
      if (group !== undefined) {
        groups.push(group)
      }
    }
  }
  const fallbackTotal = groups.reduce((sum, group) => sum + group.items.length, 0)
  const totalRaw = raw.total
  const total =
    typeof totalRaw === 'number' && Number.isFinite(totalRaw) && totalRaw >= 0 ? Math.floor(totalRaw) : fallbackTotal
  const result: SearchResult = { groups, total }
  const degraded = normalizeBool(raw.degraded)
  if (degraded === true) {
    result.degraded = true
  }
  const reason = parseDegradeReason(raw.degradeReason ?? raw.degrade_reason)
  if (reason !== undefined) {
    result.degradeReason = reason
  }
  return result
}

/**
 * 按授权集合过滤可检索域（`perm` 缺省一律可见）。
 *
 * @param domains 域清单。
 * @param granted 授权权限码集合。
 * @returns 可见域（新数组）。
 */
export function filterAccessibleDomains(
  domains: readonly SearchDomain[],
  granted: ReadonlySet<string>,
): SearchDomain[] {
  return domains.filter((domain) => domain.perm === undefined || domain.perm === '' || granted.has(domain.perm))
}

/**
 * 取域展示名（未登记回落键名）。
 *
 * @param domains 域清单。
 * @param key 域标识。
 * @returns 域名称。
 */
export function domainLabelOf(domains: readonly SearchDomain[], key: string): string {
  return domains.find((domain) => domain.key === key)?.label ?? key
}

/**
 * 判断关键词是否为空（仅 `trim` 后为空为真）。
 *
 * @param keyword 关键词。
 * @returns 是否为空。
 */
export function isBlankKeyword(keyword: unknown): boolean {
  return typeof keyword !== 'string' || keyword.trim() === ''
}

/**
 * 归一关键词（去首尾空白并按上限截断）。
 *
 * @param keyword 原始关键词。
 * @param max 长度上限（码点，缺省 `SEARCH_KEYWORD_MAX`）。
 * @returns 归一关键词。
 */
export function normalizeKeyword(keyword: unknown, max: number = SEARCH_KEYWORD_MAX): string {
  if (typeof keyword !== 'string') {
    return ''
  }
  const trimmed = keyword.trim()
  const limit = Math.max(0, Math.floor(max))
  return [...trimmed].slice(0, limit).join('')
}

/**
 * 夹取页码到 `1 ~ SEARCH_PAGE_DEPTH_MAX`。
 *
 * @param page 原始页码。
 * @returns 夹取后的页码。
 */
export function clampSearchPage(page: unknown): number {
  const numeric = typeof page === 'number' ? page : Number(page)
  if (!Number.isFinite(numeric) || numeric < 1) {
    return 1
  }
  return Math.min(Math.floor(numeric), SEARCH_PAGE_DEPTH_MAX)
}

/**
 * 夹取页长到 `1 ~ SEARCH_PAGE_SIZE_MAX`（非法回落缺省）。
 *
 * @param size 原始页长。
 * @returns 夹取后的页长。
 */
export function clampSearchPageSize(size: unknown): number {
  const numeric = typeof size === 'number' ? size : Number(size)
  if (!Number.isFinite(numeric) || numeric < 1) {
    return SEARCH_PAGE_SIZE_DEFAULT
  }
  return Math.min(Math.floor(numeric), SEARCH_PAGE_SIZE_MAX)
}

/**
 * 构造全局搜索参数（与后端 `GET /search/global` 契约同源）。
 *
 * @param query 查询条件。
 * @returns 查询参数对象。
 */
export function buildGlobalParams(query: SearchGlobalQuery): {
  q: string
  types?: string
  page: number
  size: number
} {
  const params: { q: string; types?: string; page: number; size: number } = {
    q: normalizeKeyword(query.keyword),
    page: clampSearchPage(query.page),
    size: clampSearchPageSize(query.pageSize),
  }
  const types = (query.types ?? []).map((type) => normalizeText(type)).filter((type): type is string => type !== undefined)
  if (types.length > 0) {
    params.types = types.join(',')
  }
  return params
}

/**
 * 构造审计日志检索参数（与后端 `GET /search/logs` 契约同源）。
 *
 * @param query 查询条件。
 * @returns 查询参数对象。
 */
export function buildLogParams(query: SearchLogQuery): {
  q: string
  log_type?: string
  start_time: string
  end_time: string
  page: number
  size: number
} {
  const params: {
    q: string
    log_type?: string
    start_time: string
    end_time: string
    page: number
    size: number
  } = {
    q: normalizeKeyword(query.keyword),
    start_time: query.start,
    end_time: query.end,
    page: clampSearchPage(query.page),
    size: clampSearchPageSize(query.pageSize),
  }
  const logType = normalizeText(query.logType)
  if (logType !== undefined) {
    params.log_type = logType
  }
  return params
}

/**
 * 构造文件内容检索参数（与后端 `GET /search/files` 契约同源）。
 *
 * @param query 查询条件。
 * @returns 查询参数对象。
 */
export function buildFileParams(query: SearchFileQuery): {
  q: string
  file_type?: string
  page: number
  size: number
} {
  const params: { q: string; file_type?: string; page: number; size: number } = {
    q: normalizeKeyword(query.keyword),
    page: clampSearchPage(query.page),
    size: clampSearchPageSize(query.pageSize),
  }
  const fileType = normalizeText(query.fileType)
  if (fileType !== undefined) {
    params.file_type = fileType
  }
  return params
}

/**
 * 计算两个时间点相差的自然日（向上取整，非法 / 倒序回落 `0`）。
 *
 * @param start 起点。
 * @param end 终点。
 * @returns 天数。
 */
export function diffDays(start: unknown, end: unknown): number {
  const left = new Date(String(start)).getTime()
  const right = new Date(String(end)).getTime()
  if (!Number.isFinite(left) || !Number.isFinite(right) || right <= left) {
    return 0
  }
  return Math.ceil((right - left) / 86_400_000)
}

/**
 * 校验审计日志时间范围（必填且单次不超过上限）。
 *
 * @param range 时间范围。
 * @param maxDays 上限天数（缺省 `SEARCH_LOG_RANGE_MAX_DAYS`）。
 * @returns 校验结果。
 */
export function validateLogRange(
  range: SearchRange,
  maxDays: number = SEARCH_LOG_RANGE_MAX_DAYS,
): SearchValidation {
  const start = normalizeText(range.start)
  const end = normalizeText(range.end)
  if (start === undefined || end === undefined) {
    return { valid: false, message: SEARCH_LOG_RANGE_REQUIRED_TEXT }
  }
  const limit = Math.max(1, Math.floor(maxDays))
  if (diffDays(start, end) > limit) {
    return { valid: false, message: SEARCH_LOG_RANGE_EXCEED_TEXT }
  }
  return { valid: true }
}

/**
 * 按文档类型分组（域顺序按传入域清单保序，未知域追加末尾）。
 *
 * @param hits 命中数组。
 * @param domains 域清单（用于取展示名与排序）。
 * @returns 分组结果。
 */
export function groupHits(hits: readonly SearchHit[], domains: readonly SearchDomain[] = []): SearchGroup[] {
  const buckets = new Map<string, SearchHit[]>()
  for (const hit of hits) {
    const bucket = buckets.get(hit.docType)
    if (bucket === undefined) {
      buckets.set(hit.docType, [hit])
    } else {
      bucket.push(hit)
    }
  }
  const ordered: SearchGroup[] = []
  for (const domain of domains) {
    const items = buckets.get(domain.key)
    if (items !== undefined) {
      ordered.push({ key: domain.key, label: domain.label, items })
      buckets.delete(domain.key)
    }
  }
  for (const [key, items] of buckets) {
    ordered.push({ key, label: domainLabelOf(domains, key), items })
  }
  return ordered
}

/**
 * 取即时建议（各域 Top N 并截断到总量上限）。
 *
 * @param hits 命中数组。
 * @param perDomain 各域上限（缺省 `SEARCH_SUGGEST_PER_DOMAIN`）。
 * @param total 总量上限（缺省 `SEARCH_SUGGEST_LIMIT`）。
 * @returns 建议命中（新数组）。
 */
export function topHits(
  hits: readonly SearchHit[],
  perDomain: number = SEARCH_SUGGEST_PER_DOMAIN,
  total: number = SEARCH_SUGGEST_LIMIT,
): SearchHit[] {
  const perLimit = Math.max(0, Math.floor(perDomain))
  const totalLimit = Math.max(0, Math.floor(total))
  const counters = new Map<string, number>()
  const out: SearchHit[] = []
  for (const hit of hits) {
    if (out.length >= totalLimit) {
      break
    }
    const used = counters.get(hit.docType) ?? 0
    if (used >= perLimit) {
      continue
    }
    counters.set(hit.docType, used + 1)
    out.push(hit)
  }
  return out
}

/**
 * 归一最近搜索（过滤空串、去重、截断上限）。
 *
 * @param value 原始数组。
 * @param max 上限（缺省 `SEARCH_RECENT_MAX`）。
 * @returns 归一关键词数组。
 */
export function normalizeRecentKeywords(value: unknown, max: number = SEARCH_RECENT_MAX): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  const limit = Math.max(0, Math.floor(max))
  const seen = new Set<string>()
  const out: string[] = []
  for (const entry of value) {
    const keyword = normalizeKeyword(entry)
    if (keyword === '' || seen.has(keyword)) {
      continue
    }
    seen.add(keyword)
    out.push(keyword)
    if (out.length >= limit) {
      break
    }
  }
  return out
}

/**
 * 追加最近搜索（去重后置顶并按上限截断）。
 *
 * @param list 现有列表。
 * @param keyword 关键词。
 * @param max 上限（缺省 `SEARCH_RECENT_MAX`）。
 * @returns 新列表。
 */
export function addRecentKeyword(
  list: readonly string[],
  keyword: unknown,
  max: number = SEARCH_RECENT_MAX,
): string[] {
  const normalized = normalizeKeyword(keyword)
  if (normalized === '') {
    return normalizeRecentKeywords(list, max)
  }
  const rest = normalizeRecentKeywords(list, max).filter((item) => item !== normalized)
  return normalizeRecentKeywords([normalized, ...rest], max)
}

/**
 * 移除最近搜索。
 *
 * @param list 现有列表。
 * @param keyword 关键词。
 * @returns 新列表。
 */
export function removeRecentKeyword(list: readonly string[], keyword: unknown): string[] {
  const normalized = normalizeKeyword(keyword)
  return list.filter((item) => item !== normalized)
}

/**
 * 命中稳定键（`${docType}:${bizId}`）。
 *
 * @param hit 命中项。
 * @returns 稳定键。
 */
export function hitKey(hit: SearchHit): string {
  return `${hit.docType}:${hit.bizId}`
}

/**
 * 命中跳转目标（路由映射归宿主）。
 *
 * @param hit 命中项。
 * @returns 跳转目标。
 */
export function hitRouteTarget(hit: SearchHit): { docType: string; bizId: string } {
  return { docType: hit.docType, bizId: hit.bizId }
}

/**
 * 解析降级标记。
 *
 * @param value 原始标记。
 * @returns 是否降级。
 */
export function parseDegraded(value: unknown): boolean {
  return normalizeBool(value) === true
}

/**
 * 解析降级原因（非白名单回落 `undefined`）。
 *
 * @param value 原始原因。
 * @returns 降级原因或 `undefined`。
 */
export function parseDegradeReason(value: unknown): SearchDegradeReason | undefined {
  const text = typeof value === 'string' ? value.trim() : ''
  return (SEARCH_DEGRADE_REASONS as readonly string[]).includes(text)
    ? (text as SearchDegradeReason)
    : undefined
}

/**
 * 判断是否为检索错误码（`10101 ~ 10107`）。
 *
 * @param value 原始错误码。
 * @returns 是否落在检索段。
 */
export function isSearchErrorCode(value: unknown): boolean {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(numeric) && numeric >= 10101 && numeric <= 10107
}

/**
 * 检索错误码 → 中文文案（未知回落「检索失败」）。
 *
 * @param code 错误码。
 * @returns 文案。
 */
export function resolveSearchErrorText(code: unknown): string {
  switch (code) {
    case 10101:
      return '检索服务不可用'
    case 10102:
      return '检索超时'
    case 10103:
      return SEARCH_DEGRADE_TEXT
    case 10104:
      return '目标索引未就绪'
    case 10106:
      return SEARCH_FILE_UNSEARCHABLE_TEXT
    case 10107:
      return '检索时间范围超限'
    default:
      return '检索失败'
  }
}
