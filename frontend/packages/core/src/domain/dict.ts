/**
 * 领域纯函数：字典字段（归一 / 版本比对 / 大小字典 / 树 / 条件组 / 参数与缓存键 / 标签翻译 / 错误码）。
 *
 * 框架无关、不触 DOM、不请求，同输入同输出；后端线参数与结果形状同源（`snake_case` 兼容归一）。
 */

/** 大小字典阈值（条目数 ≥ 阈值即超大字典）。 */
export const DICT_LARGE_THRESHOLD = 2000
/** 探针条数上限（首次取数以该值判别大小字典，与后端 `DICT_PROBE_LIMIT` 同源）。 */
export const DICT_PROBE_LIMIT = 2001
/** 远程搜索防抖（毫秒，与组织搜索同口径）。 */
export const DICT_SEARCH_DEBOUNCE = 300
/** 默认语言（与后端 `DEFAULT_LOCALE` 同源）。 */
export const DICT_DEFAULT_LOCALE = 'zh-CN'
/** 支持语言清单（与后端 `SUPPORTED_LOCALES` 同源）。 */
export const DICT_SUPPORTED_LOCALES: readonly string[] = ['zh-CN', 'en-US']
/** 类型缓存条数上限（LRU 淘汰）。 */
export const DICT_CACHE_MAX = 200
/** 子集 label 缓存条数上限。 */
export const DICT_SUBSET_MAX = 1000
/** 本地二次缓存键前缀（`utils` 落点使用）。 */
export const DICT_STORAGE_PREFIX = 'bms:dict'
/** 本地二次缓存体积上限（JSON 字符数；超限不写）。 */
export const DICT_STORAGE_MAX_BYTES = 256 * 1024
/** 空值占位。 */
export const DICT_EMPTY_VALUE = '—'
/** 只读多值连接符。 */
export const DICT_JOIN = '、'
/** 占位文案（数据通路未就绪）。 */
export const DICT_PLACEHOLDER_TEXT = '字典数据未就绪（占位）'
/** 空态文案。 */
export const DICT_EMPTY_TEXT = '暂无字典数据'
/** 无匹配文案。 */
export const DICT_NO_MATCH_TEXT = '无匹配数据'
/** 上限提示前缀。 */
export const DICT_LIMIT_TEXT_PREFIX = '最多选择'
/** 字典错误码文案（40101 ~ 40103，与后端错误码分段同源）。 */
export const DICT_ERROR_TEXTS: Readonly<Record<number, string>> = {
  40101: '字典数据源不可用',
  40102: '字典类型不存在',
  40103: '不支持的语言',
}
/** 条件组最大嵌套深度（与后端引擎口径一致）。 */
export const DICT_CONDITION_MAX_DEPTH = 2
/** 高级查询单页条数上限。 */
export const DICT_QUERY_PAGE_MAX = 100
/** 高级查询缺省页长。 */
export const DICT_QUERY_PAGE_SIZE = 20
/** 字典条目状态。 */
export const DICT_STATUSES = ['enabled', 'disabled'] as const
/** 操作符清单（后端白名单同源）。 */
export const DICT_OPERATORS = [
  'eq',
  'ne',
  'contains',
  'not_contains',
  'starts_with',
  'between',
  'gt',
  'lt',
  'is_null',
  'not_null',
  'in',
  'not_in',
] as const
/** 按数据类型派生的默认操作符集（后端 `DICT_OPERATORS_BY_TYPE` 同源）。 */
export const DICT_OPERATORS_BY_TYPE: Readonly<Record<string, readonly DictOperator[]>> = {
  text: ['eq', 'ne', 'contains', 'not_contains', 'starts_with', 'is_null', 'not_null', 'in', 'not_in'],
  number: ['eq', 'ne', 'gt', 'lt', 'between', 'is_null', 'not_null', 'in', 'not_in'],
  date: ['eq', 'ne', 'gt', 'lt', 'between', 'is_null', 'not_null'],
  enum: ['eq', 'ne', 'in', 'not_in', 'is_null', 'not_null'],
  bool: ['eq', 'ne', 'is_null', 'not_null'],
}
/** 条件组固定可查字段（除扩展属性外）。 */
export const DICT_ADV_FIXED_FIELDS: readonly string[] = ['value', 'label', 'code', 'sort', 'status']
/** 操作符显示文案。 */
export const DICT_OPERATOR_TEXTS: Readonly<Record<string, string>> = {
  eq: '等于',
  ne: '不等于',
  contains: '包含',
  not_contains: '不包含',
  starts_with: '开头是',
  between: '介于',
  gt: '大于',
  lt: '小于',
  is_null: '为空',
  not_null: '不为空',
  in: '属于',
  not_in: '不属于',
}

/** 字典条目状态。 */
export type DictStatus = (typeof DICT_STATUSES)[number]
/** 条件操作符。 */
export type DictOperator = (typeof DICT_OPERATORS)[number]
/** 高级查询目标（取项 / 业务筛选）。 */
export type DictTarget = 'items' | 'business'
/** 属性数据类型。 */
export type DictDataType = 'text' | 'number' | 'date' | 'enum' | 'bool'

/** 字典条目（展示最小面；兼容后端 `snake_case`）。 */
export interface DictItem {
  /** 条目值。 */
  value: string
  /** 条目标签（按 locale）。 */
  label: string
  /** 条目编码。 */
  code: string
  /** 级联父值（引用父条目 value；缺省顶层）。 */
  parentId?: string
  /** 排序值。 */
  sort: number
  /** 状态（`enabled` / `disabled`）。 */
  status: DictStatus
  /** 语义色（可空）。 */
  color?: string
}

/** 单类型取数结果（`items === null` 表示版本一致，复用本地缓存）。 */
export interface DictTypeResult {
  /** 当前全局版本号。 */
  version: number
  /** 条目集；`null` 表示版本一致。 */
  items: DictItem[] | null
  /** 是否还有更多（超过 limit 截断）。 */
  hasMore: boolean
  /** 命中总数。 */
  total: number
}

/** 批量取数结果（内层 `null` 表示该类型版本一致）。 */
export interface DictBatchResult {
  /** 当前全局版本号。 */
  version: number
  /** 按类型的取数结果。 */
  items: Record<string, DictTypeResult | null>
}

/** 单类型查询参数（线参数由 `buildDictTypeQuery` 单一构造）。 */
export interface DictTypeQuery {
  /** 字典类型码。 */
  dictType: string
  /** 客户端本地版本号（一致时后端返回 `items=null`）。 */
  version?: number
  /** 关键字（label / value / code）。 */
  keyword?: string
  /** 级联父值（空串 = 顶层）。 */
  parentId?: string
  /** 指定 value 子集（批量翻译）。 */
  values?: readonly string[]
  /** 返回条数上限（探针传 `DICT_PROBE_LIMIT`）。 */
  limit?: number
}

/** 批量查询参数。 */
export interface DictBatchQuery {
  /** 字典类型码序列。 */
  types: readonly string[]
  /** 客户端本地版本号。 */
  version?: number
  /** 语言（缺省默认语言）。 */
  locale?: string
}

/** 属性 schema（高级查询条件字段）。 */
export interface DictAttrSchema {
  /** 属性键。 */
  attrKey: string
  /** 属性名（按 locale）。 */
  name: string
  /** 数据类型。 */
  dataType: DictDataType
  /** 可用操作符。 */
  operators: readonly DictOperator[]
  /** 值控件（可选）。 */
  widget?: string
  /** enum 选项集。 */
  options?: readonly { label: string; value: string }[]
  /** 排序值。 */
  sort: number
  /** 属性来源（`platform` / `tenant`）。 */
  scope: string
}

/** 条件构建件字段项（固定字段 + 属性）。 */
export interface DictAttrFieldOption {
  /** 字段名（固定字段或 `attr.<key>`）。 */
  field: string
  /** 显示名。 */
  label: string
  /** 数据类型。 */
  dataType: DictDataType
  /** 可用操作符。 */
  operators: readonly DictOperator[]
  /** enum 选项集。 */
  options?: readonly { label: string; value: string }[]
}

/** 查询提供者（发现—选择—调用）。 */
export interface DictQueryProvider {
  /** 提供者标识。 */
  key: string
  /** 显示名。 */
  name: string
  /** 目标（`items` / `business`）。 */
  target: DictTarget
  /** 适用字典类型（空 = 全部）。 */
  dictTypes: readonly string[]
  /** 参数 JSON Schema 子集。 */
  paramSchema: Record<string, unknown>
}

/** 查询方案（三级作用域）。 */
export interface DictQueryScheme {
  /** 方案 ID（新建为空）。 */
  id?: number
  /** 方案名。 */
  name: string
  /** 作用域（个人 / 租户 / 平台）。 */
  scope: 'user' | 'tenant' | 'platform'
  /** 目标。 */
  target: DictTarget
  /** 字典类型（`target=items`）。 */
  dictType?: string
  /** 查询提供者键。 */
  providerKey?: string
  /** 条件组。 */
  conditions?: DictConditionGroup
  /** 额外参数。 */
  params?: Record<string, unknown>
  /** 是否默认方案。 */
  isDefault: boolean
  /** 是否共享。 */
  shared: boolean
}

/** 条件项。 */
export interface DictConditionItem {
  /** 字段（固定字段或 `attr.<key>`）。 */
  field: string
  /** 操作符。 */
  operator: DictOperator
  /** 条件值（按操作符联动）。 */
  value?: unknown
}

/** 条件组（AND / OR 分组树）。 */
export interface DictConditionGroup {
  /** 组内关系。 */
  logic: 'AND' | 'OR'
  /** 子条件 / 子组。 */
  children: (DictConditionItem | DictConditionGroup)[]
}

/** 高级查询结果（取项分页 / 业务筛选行）。 */
export interface DictAdvQueryResult {
  /** 字典条目（`target=items`）。 */
  items: DictItem[]
  /** 业务记录（`target=business`）。 */
  rows: Record<string, unknown>[]
  /** 命中总数。 */
  total: number
  /** 页码（自 1）。 */
  page: number
  /** 页长。 */
  size: number
}

/** 树节点（结构兼容级联件 `CascadeOption`）。 */
export interface DictTreeNode {
  /** 节点值。 */
  value: string
  /** 节点文案。 */
  label: string
  /** 是否禁用。 */
  disabled?: boolean
  /** 子节点。 */
  children?: DictTreeNode[]
}

/**
 * 归一单条字典条目（兼容 `snake_case`；`value` 缺失剔除）。
 *
 * @param raw 原始条目。
 * @returns 归一结果；非法返回 `undefined`。
 */
export function normalizeDictItem(raw: unknown): DictItem | undefined {
  if (raw === null || typeof raw !== 'object') {
    return undefined
  }
  const record = raw as Record<string, unknown>
  const value = record.value
  if (typeof value !== 'string' || value === '') {
    return undefined
  }
  const label = typeof record.label === 'string' ? record.label : value
  const parentRaw = record.parentId ?? record.parent_id
  const statusRaw = record.status
  const status: DictStatus = statusRaw === 'disabled' ? 'disabled' : 'enabled'
  const colorRaw = record.color
  const sortRaw = record.sort
  const item: DictItem = {
    value,
    label,
    code: typeof record.code === 'string' ? record.code : '',
    sort: typeof sortRaw === 'number' && Number.isFinite(sortRaw) ? sortRaw : 0,
    status,
  }
  if (typeof parentRaw === 'string' && parentRaw !== '') {
    item.parentId = parentRaw
  }
  if (typeof colorRaw === 'string' && colorRaw !== '') {
    item.color = colorRaw
  }
  return item
}

/**
 * 归一字典条目列表（脏项剔除）。
 *
 * @param raw 原始列表。
 * @returns 归一后的条目列表。
 */
export function normalizeDictItems(raw: unknown): DictItem[] {
  if (!Array.isArray(raw)) {
    return []
  }
  const items: DictItem[] = []
  for (const entry of raw) {
    const item = normalizeDictItem(entry)
    if (item !== undefined) {
      items.push(item)
    }
  }
  return items
}

/**
 * 归一单类型取数结果（保留 `items=null` 的版本一致语义）。
 *
 * @param raw 原始结果。
 * @returns 归一结果。
 */
export function normalizeDictTypeResult(raw: unknown): DictTypeResult {
  if (raw === null || typeof raw !== 'object') {
    return { version: 0, items: [], hasMore: false, total: 0 }
  }
  const record = raw as Record<string, unknown>
  const version = toInt(record.version)
  const rawItems = record.items
  if (rawItems === null) {
    return { version, items: null, hasMore: false, total: 0 }
  }
  const items = normalizeDictItems(rawItems)
  const totalRaw = record.total
  const hasMoreRaw = record.hasMore ?? record.has_more
  return {
    version,
    items,
    hasMore: hasMoreRaw === true,
    total: typeof totalRaw === 'number' && Number.isFinite(totalRaw) ? totalRaw : items.length,
  }
}

/**
 * 归一批量取数结果（内层 `null` 保留）。
 *
 * @param raw 原始结果。
 * @returns 归一结果。
 */
export function normalizeDictBatchResult(raw: unknown): DictBatchResult {
  if (raw === null || typeof raw !== 'object') {
    return { version: 0, items: {} }
  }
  const record = raw as Record<string, unknown>
  const version = toInt(record.version)
  const rawItems = record.items
  const items: Record<string, DictTypeResult | null> = {}
  if (rawItems !== null && typeof rawItems === 'object' && !Array.isArray(rawItems)) {
    for (const [name, entry] of Object.entries(rawItems as Record<string, unknown>)) {
      items[name] = entry === null ? null : normalizeDictTypeResult(entry)
    }
  }
  return { version, items }
}

/**
 * 受控值归一（单值取首值、多选包数组、去重、空值剔除、统一字符串）。
 *
 * @param value 受控值。
 * @param multiple 是否多选。
 * @returns 归一后的值列表。
 */
export function normalizeDictValues(value: unknown, multiple: boolean): string[] {
  if (value === undefined || value === null || value === '') {
    return []
  }
  const rawList = Array.isArray(value) ? value : multiple ? [value] : [value]
  const result: string[] = []
  for (const entry of rawList) {
    if (entry === undefined || entry === null || entry === '') {
      continue
    }
    const text = typeof entry === 'string' ? entry : String(entry)
    if (text !== '' && !result.includes(text)) {
      result.push(text)
    }
  }
  return multiple ? result : result.slice(0, 1)
}

/**
 * 是否超大字典（总数达阈值或探针截断）。
 *
 * @param result 取数结果。
 * @returns 超大字典为 `true`。
 */
export function isLargeDict(result: DictTypeResult): boolean {
  return result.hasMore || result.total >= DICT_LARGE_THRESHOLD
}

/**
 * 选择与上限（多选追加去重并按上限截断；单选整体替换）。
 *
 * @param current 当前值列表。
 * @param incoming 新增值列表。
 * @param options 选择选项（多选 / 上限）。
 * @returns 结果值列表与是否超限。
 */
export function applyDictSelection(
  current: readonly string[],
  incoming: readonly string[],
  options: { multiple: boolean; limit: number },
): { values: string[]; exceeded: boolean } {
  if (!options.multiple) {
    const value = incoming[0]
    return { values: value === undefined ? [] : [value], exceeded: false }
  }
  const values = [...current]
  let exceeded = false
  for (const value of incoming) {
    if (values.includes(value)) {
      continue
    }
    if (options.limit > 0 && values.length >= options.limit) {
      exceeded = true
      continue
    }
    values.push(value)
  }
  return { values, exceeded }
}

/**
 * 移除值（不存在时原样返回）。
 *
 * @param values 当前值列表。
 * @param value 待移除值。
 * @returns 新值列表。
 */
export function removeDictValue(values: readonly string[], value: string): string[] {
  return values.filter((entry) => entry !== value)
}

/**
 * 按值取条目（未命中返回 `undefined`）。
 *
 * @param items 条目列表。
 * @param value 值。
 * @returns 条目；未命中 `undefined`。
 */
export function findDictItem(items: readonly DictItem[], value: string): DictItem | undefined {
  return items.find((item) => item.value === value)
}

/**
 * 按 value 合并条目（入参覆盖同名项；保序：基础在前、新增追加）。
 *
 * @param base 基础条目。
 * @param incoming 增量条目。
 * @returns 合并后的条目列表。
 */
export function mergeDictItems(base: readonly DictItem[], incoming: readonly DictItem[]): DictItem[] {
  const merged = [...base]
  for (const item of incoming) {
    const index = merged.findIndex((existing) => existing.value === item.value)
    if (index >= 0) {
      merged[index] = item
    } else {
      merged.push(item)
    }
  }
  return merged
}

/**
 * 按值取标签（未命中返回 `undefined`）。
 *
 * @param items 条目列表。
 * @param value 值。
 * @returns 标签；未命中 `undefined`。
 */
export function dictLabelOf(items: readonly DictItem[], value: string): string | undefined {
  return items.find((item) => item.value === value)?.label
}

/**
 * 多值标签翻译（「、」连接；未命中回退原值）。
 *
 * @param items 条目列表。
 * @param values 值列表。
 * @returns 翻译文本。
 */
export function dictTranslateValues(items: readonly DictItem[], values: readonly string[]): string {
  return values.map((value) => dictLabelOf(items, value) ?? value).join(DICT_JOIN)
}

/**
 * 本地搜索（label / value / code 包含匹配；空关键词返回全部）。
 *
 * @param items 条目列表。
 * @param keyword 关键词。
 * @returns 命中条目。
 */
export function filterDictItems(items: readonly DictItem[], keyword: string): DictItem[] {
  const text = keyword.trim().toLowerCase()
  if (text === '') {
    return [...items]
  }
  return items.filter(
    (item) =>
      item.label.toLowerCase().includes(text) ||
      item.value.toLowerCase().includes(text) ||
      item.code.toLowerCase().includes(text),
  )
}

/**
 * 条目是否禁用（`status=disabled`）。
 *
 * @param item 条目。
 * @returns 禁用为 `true`。
 */
export function isDictItemDisabled(item: DictItem): boolean {
  return item.status === 'disabled'
}

/**
 * 构建树节点（`parentId` 分组递归；孤儿提升顶层；深度上限 16 防环）。
 *
 * @param items 条目列表。
 * @returns 树节点列表。
 */
export function toDictTreeNodes(items: readonly DictItem[]): DictTreeNode[] {
  const nodeMap = new Map<string, DictTreeNode>()
  for (const item of items) {
    nodeMap.set(item.value, {
      value: item.value,
      label: item.label,
      disabled: isDictItemDisabled(item),
    })
  }
  const roots: DictTreeNode[] = []
  const attach = (node: DictTreeNode, depth: number): void => {
    if (depth > 16) {
      return
    }
    const children = items.filter((item) => item.parentId === node.value).sort((a, b) => a.sort - b.sort)
    if (children.length === 0) {
      return
    }
    node.children = children.map((child) => nodeMap.get(child.value) as DictTreeNode)
    for (const child of node.children) {
      attach(child, depth + 1)
    }
  }
  const sorted = [...items].sort((a, b) => a.sort - b.sort)
  for (const item of sorted) {
    const hasParent = item.parentId !== undefined && nodeMap.has(item.parentId)
    if (!hasParent) {
      roots.push(nodeMap.get(item.value) as DictTreeNode)
    }
  }
  for (const root of roots) {
    attach(root, 1)
  }
  return roots
}

/**
 * 构建级联件选项（结构同 `DictTreeNode`）。
 *
 * @param items 条目列表。
 * @returns 级联选项列表。
 */
export function toDictCascadeOptions(items: readonly DictItem[]): DictTreeNode[] {
  return toDictTreeNodes(items)
}

/**
 * 类型缓存键（`{locale}:{type}`）。
 *
 * @param locale 语言。
 * @param dictType 字典类型码。
 * @returns 缓存键。
 */
export function dictCacheKey(locale: string, dictType: string): string {
  return `${locale}:${dictType}`
}

/**
 * 子集缓存键（`{locale}:{type}:{value}`）。
 *
 * @param locale 语言。
 * @param dictType 字典类型码。
 * @param value 条目值。
 * @returns 子集缓存键。
 */
export function dictSubsetKey(locale: string, dictType: string, value: string): string {
  return `${locale}:${dictType}:${value}`
}

/**
 * 本地二次缓存键（`bms:dict:{locale}:{type}`）。
 *
 * @param locale 语言。
 * @param dictType 字典类型码。
 * @returns 本地缓存键。
 */
export function dictStorageKey(locale: string, dictType: string): string {
  return `${DICT_STORAGE_PREFIX}:${locale}:${dictType}`
}

/**
 * 构造单类型线参数（非空才传）。
 *
 * @param input 查询入参。
 * @returns 线参数。
 */
export function buildDictTypeQuery(input: DictTypeQuery): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  if (input.version !== undefined && input.version > 0) {
    params.version = input.version
  }
  const keyword = input.keyword?.trim()
  if (keyword !== undefined && keyword !== '') {
    params.keyword = keyword
  }
  if (input.parentId !== undefined) {
    params.parent_id = input.parentId
  }
  if (input.values !== undefined && input.values.length > 0) {
    params.values = [...input.values].join(',')
  }
  if (input.limit !== undefined && input.limit > 0) {
    params.limit = input.limit
  }
  return params
}

/**
 * 构造批量线参数。
 *
 * @param types 类型序列。
 * @param version 版本号（可选）。
 * @param locale 语言（可选）。
 * @returns 请求体。
 */
export function buildDictBatchQuery(
  types: readonly string[],
  version?: number,
  locale?: string,
): Record<string, unknown> {
  const body: Record<string, unknown> = { types: [...types] }
  if (version !== undefined && version > 0) {
    body.version = version
  }
  if (locale !== undefined && locale !== '') {
    body.locale = locale
  }
  return body
}

/**
 * 构造高级查询请求体。
 *
 * @param target 目标。
 * @param payload 载荷。
 * @returns 请求体。
 */
export function buildDictAdvQuery(
  target: DictTarget,
  payload: {
    conditions?: DictConditionGroup
    provider?: string
    params?: Record<string, unknown>
    page?: number
    size?: number
  },
): Record<string, unknown> {
  const body: Record<string, unknown> = { target }
  if (payload.conditions !== undefined) {
    body.conditions = payload.conditions
  }
  if (payload.provider !== undefined && payload.provider !== '') {
    body.provider = payload.provider
  }
  if (payload.params !== undefined) {
    body.params = payload.params
  }
  body.page = clampDictPage(payload.page)
  body.size = clampDictPageSize(payload.size)
  return body
}

/**
 * 按数据类型取默认操作符集。
 *
 * @param dataType 数据类型。
 * @returns 操作符列表。
 */
export function defaultOperatorsOf(dataType: string): readonly DictOperator[] {
  return DICT_OPERATORS_BY_TYPE[dataType] ?? DICT_OPERATORS_BY_TYPE.text ?? []
}

/**
 * 操作符是否适用于数据类型。
 *
 * @param dataType 数据类型。
 * @param operator 操作符。
 * @returns 适用为 `true`。
 */
export function isOperatorAllowed(dataType: string, operator: string): boolean {
  return defaultOperatorsOf(dataType).includes(operator as DictOperator)
}

/**
 * 归一条件组（结构 / 深度 / 操作符校验；非法返回 `undefined`）。
 *
 * @param raw 原始条件组。
 * @returns 归一结果；非法 `undefined`。
 */
export function normalizeConditionGroup(raw: unknown): DictConditionGroup | undefined {
  if (raw === null || typeof raw !== 'object') {
    return undefined
  }
  return normalizeGroup(raw as Record<string, unknown>, 1)
}

/**
 * 条件组业务校验（字段白名单 / 操作符联动）。
 *
 * @param group 条件组。
 * @param fields 可用字段清单。
 * @returns 非法原因；合法 `undefined`。
 */
export function validateConditionGroup(group: DictConditionGroup, fields: readonly DictAttrFieldOption[]): string | undefined {
  const map = new Map(fields.map((field) => [field.field, field]))
  return validateGroup(group, map, 1)
}

/**
 * 构造固定字段项（`value` / `label` / `code` / `sort` / `status`）。
 *
 * @returns 固定字段清单。
 */
export function dictFixedFieldOptions(): DictAttrFieldOption[] {
  return [
    { field: 'value', label: '值', dataType: 'text', operators: defaultOperatorsOf('text') },
    { field: 'label', label: '标签', dataType: 'text', operators: defaultOperatorsOf('text') },
    { field: 'code', label: '编码', dataType: 'text', operators: defaultOperatorsOf('text') },
    { field: 'sort', label: '排序', dataType: 'number', operators: defaultOperatorsOf('number') },
    { field: 'status', label: '状态', dataType: 'enum', operators: defaultOperatorsOf('enum') },
  ]
}

/**
 * 属性 schema → 条件字段项。
 *
 * @param attrs 属性清单。
 * @returns 字段项列表。
 */
export function dictAttrFieldOptions(attrs: readonly DictAttrSchema[]): DictAttrFieldOption[] {
  return attrs.map((attr) => ({
    field: `attr.${attr.attrKey}`,
    label: attr.name,
    dataType: attr.dataType,
    operators: attr.operators.length > 0 ? attr.operators : defaultOperatorsOf(attr.dataType),
    options: attr.options,
  }))
}

/**
 * 归一查询方案（脏项剔除）。
 *
 * @param raw 原始方案。
 * @returns 归一结果；非法 `undefined`。
 */
export function normalizeDictQueryScheme(raw: unknown): DictQueryScheme | undefined {
  if (raw === null || typeof raw !== 'object') {
    return undefined
  }
  const record = raw as Record<string, unknown>
  const name = record.name
  const targetRaw = record.target
  if (typeof name !== 'string' || name === '' || (targetRaw !== 'items' && targetRaw !== 'business')) {
    return undefined
  }
  const scopeRaw = record.scope
  const scope: DictQueryScheme['scope'] =
    scopeRaw === 'tenant' || scopeRaw === 'platform' ? scopeRaw : 'user'
  const idRaw = record.id
  const scheme: DictQueryScheme = {
    name,
    scope,
    target: targetRaw,
    isDefault: record.isDefault === true || record.is_default === true,
    shared: record.shared === true,
  }
  if (typeof idRaw === 'number' && Number.isFinite(idRaw)) {
    scheme.id = idRaw
  }
  const dictType = record.dictType ?? record.dict_type
  if (typeof dictType === 'string' && dictType !== '') {
    scheme.dictType = dictType
  }
  const providerKey = record.providerKey ?? record.provider_key
  if (typeof providerKey === 'string' && providerKey !== '') {
    scheme.providerKey = providerKey
  }
  const conditions = normalizeConditionGroup(record.conditions)
  if (conditions !== undefined) {
    scheme.conditions = conditions
  }
  const params = record.params
  if (params !== null && typeof params === 'object' && !Array.isArray(params)) {
    scheme.params = params as Record<string, unknown>
  }
  return scheme
}

/**
 * 方案作用域优先级（个人 > 租户 > 平台）。
 *
 * @param scope 作用域。
 * @returns 优先级数值（小者优先）。
 */
export function dictSchemePriority(scope: DictQueryScheme['scope']): number {
  if (scope === 'user') {
    return 0
  }
  return scope === 'tenant' ? 1 : 2
}

/**
 * 是否字典错误码（40101 ~ 40103）。
 *
 * @param code 错误码。
 * @returns 是字典错误码为 `true`。
 */
export function isDictErrorCode(code: number | undefined): boolean {
  return code !== undefined && code >= 40101 && code <= 40103
}

/**
 * 错误码 → 文案（其余回落「字典数据源不可用」）。
 *
 * @param code 错误码。
 * @returns 文案。
 */
export function resolveDictErrorText(code: number | undefined): string {
  if (code !== undefined && DICT_ERROR_TEXTS[code] !== undefined) {
    return DICT_ERROR_TEXTS[code] as string
  }
  return DICT_ERROR_TEXTS[40101] as string
}

/**
 * 页码夹取（最小 1）。
 *
 * @param page 页码。
 * @returns 夹取后的页码。
 */
export function clampDictPage(page: number | undefined): number {
  if (page === undefined || !Number.isFinite(page) || page < 1) {
    return 1
  }
  return Math.floor(page)
}

/**
 * 页长夹取（1 ~ 100；缺省 20）。
 *
 * @param size 页长。
 * @returns 夹取后的页长。
 */
export function clampDictPageSize(size: number | undefined): number {
  if (size === undefined || !Number.isFinite(size) || size < 1) {
    return DICT_QUERY_PAGE_SIZE
  }
  return Math.min(Math.floor(size), DICT_QUERY_PAGE_MAX)
}

/**
 * 关键词是否为空（空白视为空）。
 *
 * @param keyword 关键词。
 * @returns 为空 `true`。
 */
export function isBlankDictKeyword(keyword: string | undefined): boolean {
  return keyword === undefined || keyword.trim() === ''
}

/**
 * 关键词归一（去首尾空白）。
 *
 * @param keyword 关键词。
 * @returns 归一结果。
 */
export function normalizeDictKeyword(keyword: string | undefined): string {
  return keyword === undefined ? '' : keyword.trim()
}

/**
 * 任意值 → 有限整数（失败回落 0）。
 *
 * @param value 原始值。
 * @returns 整数值。
 */
function toInt(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.floor(value)
  }
  if (typeof value === 'string' && value !== '' && !Number.isNaN(Number(value))) {
    return Math.floor(Number(value))
  }
  return 0
}

/**
 * 条件组递归归一（深度 ≤ `DICT_CONDITION_MAX_DEPTH`）。
 *
 * @param raw 原始组。
 * @param depth 当前深度（自 1）。
 * @returns 归一结果；非法 `undefined`。
 */
function normalizeGroup(raw: Record<string, unknown>, depth: number): DictConditionGroup | undefined {
  if (depth > DICT_CONDITION_MAX_DEPTH) {
    return undefined
  }
  const logicRaw = raw.logic
  const logic: 'AND' | 'OR' = logicRaw === 'OR' ? 'OR' : 'AND'
  const childrenRaw = raw.children
  if (!Array.isArray(childrenRaw)) {
    return undefined
  }
  const children: (DictConditionItem | DictConditionGroup)[] = []
  for (const entry of childrenRaw) {
    if (entry === null || typeof entry !== 'object') {
      return undefined
    }
    const record = entry as Record<string, unknown>
    if (record.children !== undefined) {
      const group = normalizeGroup(record, depth + 1)
      if (group === undefined) {
        return undefined
      }
      children.push(group)
      continue
    }
    const field = record.field
    const operator = record.operator
    if (typeof field !== 'string' || field === '' || typeof operator !== 'string') {
      return undefined
    }
    if (!DICT_OPERATORS.includes(operator as DictOperator)) {
      return undefined
    }
    const item: DictConditionItem = { field, operator: operator as DictOperator }
    if (record.value !== undefined) {
      item.value = record.value
    }
    children.push(item)
  }
  return { logic, children }
}

/**
 * 条件组递归业务校验（字段白名单 / 操作符联动）。
 *
 * @param group 条件组。
 * @param fields 字段映射。
 * @param depth 当前深度（自 1）。
 * @returns 非法原因；合法 `undefined`。
 */
function validateGroup(
  group: DictConditionGroup,
  fields: ReadonlyMap<string, DictAttrFieldOption>,
  depth: number,
): string | undefined {
  if (depth > DICT_CONDITION_MAX_DEPTH) {
    return `条件组嵌套超过 ${DICT_CONDITION_MAX_DEPTH} 层`
  }
  for (const child of group.children) {
    if ('children' in child) {
      const reason = validateGroup(child, fields, depth + 1)
      if (reason !== undefined) {
        return reason
      }
      continue
    }
    const field = fields.get(child.field)
    if (field === undefined) {
      return `字段不在白名单：${child.field}`
    }
    if (!field.operators.includes(child.operator)) {
      return `操作符 ${child.operator} 不适用于 ${field.label}`
    }
  }
  return undefined
}
