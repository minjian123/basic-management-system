/**
 * 帮助领域纯函数：上下文入参 / 线参数 / 结果归一 / 上下文键 / 层级与来源展示映射。
 *
 * 纯数据、框架无关；后端契约为 `GET /api/v1/help/context`（08_02，09_02 补 `anchor_found`）。
 * 结果**不缓存跨上下文**：上下文键用于同上下文并发合并与竞态校验。
 */

/** 解析层级（由最贴近上下文到最宽）。 */
export type HelpLevel = 'field' | 'action' | 'form' | 'module' | 'global'

/** 文章来源。 */
export type HelpSource = 'builtin' | 'product' | 'tenant'

/** 解析层级集合（顺序即解析顺序）。 */
export const HELP_LEVELS: readonly HelpLevel[] = ['field', 'action', 'form', 'module', 'global']

/** 来源集合。 */
export const HELP_SOURCES: readonly HelpSource[] = ['builtin', 'product', 'tenant']

/** 层级展示文案。 */
export const HELP_LEVEL_LABELS: Readonly<Record<HelpLevel, string>> = {
  field: '字段帮助',
  action: '动作帮助',
  form: '表单帮助',
  module: '模块帮助',
  global: '通用帮助',
}

/** 来源展示文案。 */
export const HELP_SOURCE_LABELS: Readonly<Record<HelpSource, string>> = {
  builtin: '平台内建',
  product: '产品包',
  tenant: '租户维护',
}

/** 「暂无帮助」文案（无锚点）。 */
export const HELP_EMPTY_TEXT = '暂无帮助'

/** 「暂无帮助内容」文案（有锚点无文章）。 */
export const HELP_NO_ARTICLE_TEXT = '暂无帮助内容'

/** 帮助上下文入参（组件侧 camelCase）。 */
export interface HelpContextInput {
  /** 产品段（模块级消歧）。 */
  productKey?: string
  /** 模块键（菜单锚点第 2 段）。 */
  moduleKey?: string
  /** 表单键（业务码）。 */
  formKey?: string
  /** 字段键（需同时给 `formKey`）。 */
  fieldKey?: string
  /** 动作码（动作码或完整权限码）。 */
  actionCode?: string
}

/** 命中文章（含正文）。 */
export interface HelpArticle {
  /** 文章主键。 */
  id: string
  /** 标题（后端已按语言解析）。 */
  title: string
  /** 正文（后端已清洗 HTML；前端渲染前仍过 `sanitizeHtml`）。 */
  content: string
  /** 来源。 */
  source: HelpSource
}

/** 文章摘要（相关内容）。 */
export interface HelpArticleSummary {
  /** 文章主键。 */
  id: string
  /** 标题。 */
  title: string
  /** 来源。 */
  source: HelpSource
}

/** 帮助分类。 */
export interface HelpCategory {
  /** 分类主键。 */
  id: string
  /** 分类名（后端已按语言解析）。 */
  name: string
  /** 分类路径。 */
  path: string
}

/** 解析结果（归一后）。 */
export interface HelpResult {
  /** 是否命中可展示文章。 */
  matched: boolean
  /** 是否登记了锚点（全局级不算；页面内入口显隐判据）。 */
  anchorFound: boolean
  /** 命中层级（未命中为 `undefined`）。 */
  level?: HelpLevel
  /** 命中锚点（全局级与未命中为 `undefined`）。 */
  helpKey?: string
  /** 命中文章。 */
  article?: HelpArticle
  /** 同一锚点的其余文章。 */
  related: HelpArticleSummary[]
  /** 分类列表。 */
  categories: HelpCategory[]
}

/** 帮助描述符（宿主 / 页面经 `usePageHelpContext` 派生，交给工具栏与顶栏入口）。 */
export interface HelpDescriptor {
  /** 解析上下文。 */
  context: HelpContextInput
  /** 元数据是否登记锚点（页内入口首次显隐判据；不请求即可判定）。 */
  anchorAvailable: boolean
  /** 数据通路是否就绪（缺省 true；未就绪不请求）。 */
  ready?: boolean
}

/** 空结果（未命中）。 */
export function emptyHelpResult(): HelpResult {
  return { matched: false, anchorFound: false, related: [], categories: [] }
}

/**
 * 读非空字符串（空串视为未提供）。
 *
 * @param value 原始值。
 * @returns string | undefined: 归一值。
 */
function readText(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() !== '' ? value.trim() : undefined
}

/**
 * 读主键（数字转字符串保精度）。
 *
 * @param value 原始值。
 * @returns string | undefined: 主键字符串。
 */
function readId(value: unknown): string | undefined {
  if (typeof value === 'string' && value !== '') {
    return value
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return undefined
}

/**
 * 归一来源（未知回落 `builtin`）。
 *
 * @param value 原始值。
 * @returns HelpSource: 来源。
 */
function normalizeSource(value: unknown): HelpSource {
  const text = readText(value)
  return text !== undefined && (HELP_SOURCES as readonly string[]).includes(text) ? (text as HelpSource) : 'builtin'
}

/**
 * 归一层级（未知返回 `undefined`）。
 *
 * @param value 原始值。
 * @returns HelpLevel | undefined: 层级。
 */
function normalizeLevel(value: unknown): HelpLevel | undefined {
  const text = readText(value)
  return text !== undefined && (HELP_LEVELS as readonly string[]).includes(text) ? (text as HelpLevel) : undefined
}

/**
 * 归一上下文（去首尾空白；空串视为未提供）。
 *
 * @param context 原始上下文。
 * @returns HelpContextInput: 归一上下文。
 */
export function normalizeHelpContext(context: HelpContextInput): HelpContextInput {
  const productKey = readText(context.productKey)
  const moduleKey = readText(context.moduleKey)
  const formKey = readText(context.formKey)
  const fieldKey = readText(context.fieldKey)
  const actionCode = readText(context.actionCode)
  return {
    ...(productKey === undefined ? {} : { productKey }),
    ...(moduleKey === undefined ? {} : { moduleKey }),
    ...(formKey === undefined ? {} : { formKey }),
    ...(fieldKey === undefined ? {} : { fieldKey }),
    ...(actionCode === undefined ? {} : { actionCode }),
  }
}

/**
 * 构造线参数（空值不传；字段级缺表单键时同样不传字段键）。
 *
 * @param context 上下文。
 * @returns Record<string, string>: 查询参数。
 */
export function buildHelpQuery(context: HelpContextInput): Record<string, string> {
  const normalized = normalizeHelpContext(context)
  const query: Record<string, string> = {}
  if (normalized.productKey !== undefined) {
    query.product_key = normalized.productKey
  }
  if (normalized.moduleKey !== undefined) {
    query.module_key = normalized.moduleKey
  }
  if (normalized.formKey !== undefined) {
    query.form_key = normalized.formKey
  }
  if (normalized.fieldKey !== undefined && normalized.formKey !== undefined) {
    query.field_key = normalized.fieldKey
  }
  if (normalized.actionCode !== undefined) {
    query.action_code = normalized.actionCode
  }
  return query
}

/**
 * 上下文键（同上下文并发合并与竞态校验；无上下文为只走全局级的空键）。
 *
 * @param context 上下文。
 * @returns string: 上下文键。
 */
export function helpContextKey(context: HelpContextInput): string {
  const normalized = normalizeHelpContext(context)
  return [
    normalized.productKey ?? '',
    normalized.moduleKey ?? '',
    normalized.formKey ?? '',
    normalized.fieldKey ?? '',
    normalized.actionCode ?? '',
  ].join('|')
}

/**
 * 归一文章（缺主键 / 标题视为脏项）。
 *
 * @param raw 原始数据。
 * @returns HelpArticle | undefined: 文章。
 */
function normalizeArticle(raw: unknown): HelpArticle | undefined {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined
  }
  const source = raw as Record<string, unknown>
  const id = readId(source.id)
  const title = readText(source.title)
  const content = readText(source.content)
  if (id === undefined || title === undefined || content === undefined) {
    return undefined
  }
  return { id, title, content, source: normalizeSource(source.source) }
}

/**
 * 归一文章摘要列表（脏项剔除）。
 *
 * @param raw 原始数据。
 * @returns HelpArticleSummary[]: 摘要列表。
 */
function normalizeRelated(raw: unknown): HelpArticleSummary[] {
  if (!Array.isArray(raw)) {
    return []
  }
  const items: HelpArticleSummary[] = []
  for (const entry of raw) {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      continue
    }
    const source = entry as Record<string, unknown>
    const id = readId(source.id)
    const title = readText(source.title)
    if (id === undefined || title === undefined) {
      continue
    }
    items.push({ id, title, source: normalizeSource(source.source) })
  }
  return items
}

/**
 * 归一分类列表（脏项剔除）。
 *
 * @param raw 原始数据。
 * @returns HelpCategory[]: 分类列表。
 */
function normalizeCategories(raw: unknown): HelpCategory[] {
  if (!Array.isArray(raw)) {
    return []
  }
  const items: HelpCategory[] = []
  for (const entry of raw) {
    if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
      continue
    }
    const source = entry as Record<string, unknown>
    const id = readId(source.id)
    const name = readText(source.name)
    if (id === undefined || name === undefined) {
      continue
    }
    items.push({ id, name, path: readText(source.path) ?? name })
  }
  return items
}

/**
 * 归一解析结果（缺 `anchor_found` 时回落 `matched`，兼容 09_02 之前的后端）。
 *
 * @param raw 原始响应 `data`。
 * @returns HelpResult: 归一结果。
 */
export function normalizeHelpResult(raw: unknown): HelpResult {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return emptyHelpResult()
  }
  const source = raw as Record<string, unknown>
  const article = normalizeArticle(source.article)
  const matched = article !== undefined
  const rawAnchor = source.anchor_found ?? source.anchorFound
  const anchorFound = typeof rawAnchor === 'boolean' ? rawAnchor : matched
  const level = normalizeLevel(source.level)
  const helpKey = readText(source.help_key ?? source.helpKey)
  return {
    matched,
    anchorFound,
    ...(level === undefined ? {} : { level }),
    ...(helpKey === undefined ? {} : { helpKey }),
    ...(article === undefined ? {} : { article }),
    related: normalizeRelated(source.related),
    categories: normalizeCategories(source.categories),
  }
}

/**
 * 层级展示文案（未知回落空串）。
 *
 * @param level 层级。
 * @returns string: 展示文案。
 */
export function helpLevelLabel(level: HelpLevel | undefined): string {
  return level === undefined ? '' : HELP_LEVEL_LABELS[level]
}

/**
 * 来源展示文案（未知回落空串）。
 *
 * @param source 来源。
 * @returns string: 展示文案。
 */
export function helpSourceLabel(source: HelpSource | undefined): string {
  return source === undefined ? '' : HELP_SOURCE_LABELS[source]
}
