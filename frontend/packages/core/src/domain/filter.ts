/**
 * 领域纯函数：筛选与查询方案（条件模型 / 操作符白名单 / 序列化 / 摘要 / 失效剔除 / 方案优先级）。
 *
 * 操作符白名单与序列化口径**与后端筛选契约同源**（等值直传、多值逗号、区间 `*_start`·`*_end`、
 * 布尔 `1`·`0`、`is_null` 标记）；不触 DOM、不请求。
 */

import { EMPTY_PLACEHOLDER, formatDate, formatDateTime, formatNumber } from './format'

/** 筛选操作符白名单（与后端 / 数据范围同源，11 种）。 */
export const FILTER_OPERATORS: readonly string[] = [
  'eq',
  'ne',
  'in',
  'like',
  'gt',
  'gte',
  'lt',
  'lte',
  'between',
  'is_null',
  'is_not_null',
]

/** 操作符中文标签。 */
export const FILTER_OPERATOR_LABELS: Readonly<Record<string, string>> = {
  eq: '等于',
  ne: '不等于',
  in: '属于',
  like: '包含',
  gt: '大于',
  gte: '大于等于',
  lt: '小于',
  lte: '小于等于',
  between: '介于',
  is_null: '为空',
  is_not_null: '不为空',
}

/** 多值分隔符。 */
export const FILTER_MULTI_SEPARATOR = ','

/** 缺省操作符。 */
export const FILTER_DEFAULT_OPERATOR = 'eq'

/** 条件控件暴露的常用操作符子集（高级操作符由字典高级查询承载）。 */
export const FIELD_QUERY_OPERATORS: readonly string[] = ['eq', 'in', 'like', 'between', 'is_null']

/** 关键字字段名（跨字段模糊，命中列由后端定义）。 */
export const KEYWORD_FIELD = 'keyword'

/** 区间开始后缀。 */
export const FILTER_RANGE_START_SUFFIX = '_start'

/** 区间结束后缀。 */
export const FILTER_RANGE_END_SUFFIX = '_end'

/** 空值标记后缀（`is_null`）。 */
export const FILTER_NULL_SUFFIX = '_is_null'

/** 非空标记后缀（`is_not_null`）。 */
export const FILTER_NOT_NULL_SUFFIX = '_is_not_null'

/** 区间无效文案。 */
export const FILTER_RANGE_INVALID_TEXT = '区间起始值不能大于结束值'

/** 数值无效文案。 */
export const FILTER_NUMBER_INVALID_TEXT = '请输入有效数值'

/** 失效条件提示文案。 */
export const FILTER_INVALID_HINT_TEXT = '部分筛选条件已失效，已忽略'

/** 查询方案作用域（三级）。 */
export type QuerySchemeScope = 'user' | 'tenant' | 'platform'

/** 查询方案作用域集合（顺序即展示顺序）。 */
export const QUERY_SCHEME_SCOPES: readonly QuerySchemeScope[] = ['user', 'tenant', 'platform']

/** 查询方案作用域中文标签。 */
export const QUERY_SCHEME_SCOPE_LABELS: Readonly<Record<QuerySchemeScope, string>> = {
  user: '个人',
  tenant: '租户',
  platform: '平台',
}

/** 查询方案目标。 */
export type QuerySchemeTarget = 'items' | 'business'

/** 查询方案目标集合。 */
export const QUERY_SCHEME_TARGETS: readonly QuerySchemeTarget[] = ['items', 'business']

/** 列表筛选方案目标。 */
export const QUERY_SCHEME_TARGET_BUSINESS: QuerySchemeTarget = 'business'

/** 个人方案数量上限。 */
export const SCHEME_DEFAULT_MAX = 20

/** 折叠阈值（条件数 ≤ 阈值不折叠）。 */
export const QUERY_COLLAPSE_THRESHOLD = 3

/** 宽屏一行条件数。 */
export const QUERY_MAX_PER_ROW = 3

/** 窄屏断点（低于则默认折叠并仅保留关键字）。 */
export const QUERY_NARROW_BREAKPOINT = 1024

/** 查询类字段类型。 */
export type FilterFieldType =
  'text' | 'textarea' | 'select' | 'multi_select' | 'switch' | 'number' | 'datetime' | 'date' | 'dept'

/** 查询类字段类型集合。 */
export const FILTER_FIELD_TYPES: readonly FilterFieldType[] = [
  'text',
  'textarea',
  'select',
  'multi_select',
  'switch',
  'number',
  'datetime',
  'date',
  'dept',
]

/** 字段类型 → 渲染器注册表字段类型键（经注册表 `resolveByType` 解析）。 */
export const FILTER_WIDGET_BY_TYPE: Readonly<Record<FilterFieldType, string>> = {
  text: 'text',
  textarea: 'textarea',
  select: 'select',
  multi_select: 'multi-select',
  switch: 'switch',
  number: 'number',
  datetime: 'datetime',
  date: 'date',
  dept: 'tree-select',
}

/** 单条筛选条件（与后端筛选契约同形）。 */
export interface FilterCondition {
  /** 字段名。 */
  field: string
  /** 操作符。 */
  operator: string
  /** 值。 */
  value: unknown
}

/** 条件选项。 */
export interface FilterOption {
  /** 展示文案。 */
  label: string
  /** 取值。 */
  value: unknown
}

/** 查询类字段声明（元数据 / 页面声明）。 */
export interface FilterField {
  /** 字段名。 */
  key: string
  /** 字段文案。 */
  label: string
  /** 字段类型。 */
  type: FilterFieldType
  /** 可用操作符（缺省取按类型的常用子集）。 */
  operators?: readonly string[]
  /** 候选项（字典 / 枚举）。 */
  options?: readonly FilterOption[]
  /** 默认值。 */
  defaultValue?: unknown
  /** 栅格跨度。 */
  span?: number
  /** 占位文案。 */
  placeholder?: string
  /** 是否为查询类字段（假则不渲染）。 */
  query?: boolean
  /** 组织类字段：是否含下级。 */
  includeChildren?: boolean
}

/** 条件摘要项。 */
export interface ConditionSummary {
  /** 字段名。 */
  field: string
  /** 字段文案。 */
  label: string
  /** 摘要文本。 */
  text: string
}

/** 失效剔除结果。 */
export interface ConditionPruneResult {
  /** 保留的条件。 */
  conditions: FilterCondition[]
  /** 剔除数量。 */
  removed: number
}

/** 查询方案条目（与后端方案契约同源）。 */
export interface QuerySchemeEntry {
  /** 方案标识（新建时缺省）。 */
  id?: string
  /** 方案名。 */
  name: string
  /** 作用域。 */
  scope: QuerySchemeScope
  /** 归属用户标识（个人方案）。 */
  ownerId?: string
  /** 方案目标。 */
  target: QuerySchemeTarget
  /** 字典类型（`items` 目标用）。 */
  dictType?: string
  /** 业务标识（列表筛选取表单键）。 */
  fieldKey?: string
  /** 查询提供者键（字典高级查询用）。 */
  providerKey?: string
  /** 条件清单。 */
  conditions: FilterCondition[]
  /** 附加参数。 */
  params?: Record<string, unknown>
  /** 展示配置。 */
  layout?: Record<string, unknown>
  /** 是否默认方案。 */
  isDefault?: boolean
  /** 是否共享。 */
  shared?: boolean
  /** 状态。 */
  status?: string
}

/** 值是否为空（未填条件不参与请求）。 */
function isBlank(value: unknown): boolean {
  if (value === null || value === undefined) {
    return true
  }
  if (typeof value === 'string') {
    return value.trim() === ''
  }
  if (Array.isArray(value)) {
    return value.every((item) => isBlank(item))
  }
  return false
}

/** 是否为区间操作符。 */
function isRangeOperator(operator: string): boolean {
  return operator === 'between'
}

/** 是否为空值判定操作符。 */
function isNullOperator(operator: string): boolean {
  return operator === 'is_null' || operator === 'is_not_null'
}

/**
 * 归一条件清单（脏项剔除、操作符缺省补 `eq`）。
 *
 * @param value 原始值。
 * @returns 条件清单。
 */
export function normalizeConditions(value: unknown): FilterCondition[] {
  if (!Array.isArray(value)) {
    return []
  }
  const result: FilterCondition[] = []
  for (const item of value) {
    if (item === null || typeof item !== 'object') {
      continue
    }
    const entry = item as Record<string, unknown>
    const field = typeof entry.field === 'string' ? entry.field.trim() : ''
    if (field === '') {
      continue
    }
    const operator =
      typeof entry.operator === 'string' && entry.operator !== '' ? entry.operator : FILTER_DEFAULT_OPERATOR
    result.push({ field, operator, value: entry.value })
  }
  return result
}

/**
 * 条件是否生效（已填且参与请求）。
 *
 * @param condition 条件。
 * @returns 是否生效。
 */
export function isConditionActive(condition: FilterCondition): boolean {
  if (condition.field === '') {
    return false
  }
  if (isNullOperator(condition.operator)) {
    return true
  }
  if (Array.isArray(condition.value)) {
    return !isBlank(condition.value)
  }
  return !isBlank(condition.value)
}

/**
 * 筛选出已生效条件。
 *
 * @param conditions 条件清单。
 * @returns 生效条件清单。
 */
export function filterActiveConditions(conditions: readonly FilterCondition[]): FilterCondition[] {
  return conditions.filter((condition) => isConditionActive(condition))
}

/**
 * 字段类型缺省操作符。
 *
 * @param type 字段类型。
 * @returns 操作符。
 */
export function defaultOperatorOf(type: FilterFieldType): string {
  switch (type) {
    case 'text':
    case 'textarea':
      return 'like'
    case 'multi_select':
      return 'in'
    case 'number':
    case 'date':
    case 'datetime':
      return 'between'
    default:
      return 'eq'
  }
}

/**
 * 字段声明的可用操作符（声明优先，缺省按类型常用子集）。
 *
 * @param field 字段声明。
 * @returns 操作符清单。
 */
export function operatorsOf(field: FilterField | undefined): readonly string[] {
  if (field === undefined) {
    return FIELD_QUERY_OPERATORS
  }
  if (field.operators !== undefined && field.operators.length > 0) {
    return field.operators
  }
  const preferred = defaultOperatorOf(field.type)
  return FIELD_QUERY_OPERATORS.includes(preferred)
    ? [preferred, ...FIELD_QUERY_OPERATORS.filter((item) => item !== preferred)]
    : FIELD_QUERY_OPERATORS
}

/**
 * 按字段名取字段声明。
 *
 * @param fields 字段清单。
 * @param key 字段名。
 * @returns 字段声明。
 */
export function fieldOf(fields: readonly FilterField[], key: string): FilterField | undefined {
  return fields.find((field) => field.key === key)
}

/**
 * 单条条件序列化（与后端筛选契约逐分支一致）。
 *
 * @param condition 条件。
 * @returns 查询参数片段。
 */
export function serializeCondition(condition: FilterCondition): Record<string, unknown> {
  const value = condition.value
  if (Array.isArray(value)) {
    if (isRangeOperator(condition.operator) && value.length === 2) {
      return {
        [`${condition.field}${FILTER_RANGE_START_SUFFIX}`]: value[0],
        [`${condition.field}${FILTER_RANGE_END_SUFFIX}`]: value[1],
      }
    }
    if (condition.operator === 'in') {
      return { [condition.field]: value.map((item) => String(item)).join(FILTER_MULTI_SEPARATOR) }
    }
  }
  if (condition.operator === 'is_null') {
    return { [`${condition.field}${FILTER_NULL_SUFFIX}`]: '1' }
  }
  if (condition.operator === 'is_not_null') {
    return { [`${condition.field}${FILTER_NOT_NULL_SUFFIX}`]: '1' }
  }
  return { [condition.field]: value }
}

/**
 * 条件清单序列化（同名字段后者覆盖；空条件不参与）。
 *
 * @param conditions 条件清单。
 * @returns 查询参数。
 */
export function serializeConditions(conditions: readonly FilterCondition[]): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  for (const condition of conditions) {
    if (!isConditionActive(condition)) {
      continue
    }
    Object.assign(params, serializeCondition(condition))
  }
  return params
}

/**
 * 构造列表取数查询参数（条件 + 关键字；空关键字不传）。
 *
 * @param conditions 条件清单。
 * @param keyword 关键字。
 * @returns 查询参数。
 */
export function buildQueryParams(conditions: readonly FilterCondition[], keyword?: string): Record<string, unknown> {
  const params = serializeConditions(conditions)
  if (keyword !== undefined && keyword.trim() !== '') {
    params[KEYWORD_FIELD] = keyword.trim()
  }
  return params
}

/** 值的展示文本（日期 / 数值口径复用格式化工具）。 */
function valueText(value: unknown, field: FilterField | undefined): string {
  if (isBlank(value)) {
    return EMPTY_PLACEHOLDER
  }
  if (Array.isArray(value)) {
    return value.map((item) => valueText(item, field)).join('、')
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }
  if (typeof value === 'number') {
    return formatNumber(value)
  }
  if (field !== undefined && field.options !== undefined) {
    const hit = field.options.find((option) => String(option.value) === String(value))
    if (hit !== undefined) {
      return hit.label
    }
  }
  const text = String(value)
  if (field !== undefined && (field.type === 'date' || field.type === 'datetime')) {
    return field.type === 'date' ? formatDate(text) : formatDateTime(text)
  }
  return text
}

/**
 * 单条条件的摘要文本（形如 `状态：启用`）。
 *
 * @param condition 条件。
 * @param field 字段声明。
 * @returns 摘要文本。
 */
export function conditionText(condition: FilterCondition, field: FilterField | undefined): string {
  const label = field?.label ?? condition.field
  if (condition.field === KEYWORD_FIELD) {
    return `关键字：${valueText(condition.value, undefined)}`
  }
  if (isNullOperator(condition.operator)) {
    return `${label}：${FILTER_OPERATOR_LABELS[condition.operator] ?? condition.operator}`
  }
  if (isRangeOperator(condition.operator) && Array.isArray(condition.value)) {
    const [start, end] = condition.value as [unknown, unknown]
    return `${label}：${valueText(start, field)} ~ ${valueText(end, field)}`
  }
  if (condition.operator === 'in' && Array.isArray(condition.value)) {
    return `${label}：${valueText(condition.value, field)}`
  }
  const suffix = field !== undefined && field.type === 'dept' && field.includeChildren === true ? '（含下级）' : ''
  return `${label}：${valueText(condition.value, field)}${suffix}`
}

/**
 * 条件摘要清单（仅出已生效条件）。
 *
 * @param conditions 条件清单。
 * @param fields 字段清单。
 * @returns 摘要清单。
 */
export function summarizeConditions(
  conditions: readonly FilterCondition[],
  fields: readonly FilterField[],
): ConditionSummary[] {
  return conditions
    .filter((condition) => isConditionActive(condition))
    .map((condition) => ({
      field: condition.field,
      label: fieldOf(fields, condition.field)?.label ?? condition.field,
      text: conditionText(condition, fieldOf(fields, condition.field)),
    }))
}

/**
 * 失效条件剔除（字段不存在 / 非查询类 / 选项值失效）。
 *
 * @param conditions 条件清单。
 * @param fields 字段清单（空清单表示无元数据，不做剔除）。
 * @returns 保留条件与剔除计数。
 */
export function pruneConditions(
  conditions: readonly FilterCondition[],
  fields: readonly FilterField[],
): ConditionPruneResult {
  if (fields.length === 0) {
    return { conditions: [...conditions], removed: 0 }
  }
  const kept: FilterCondition[] = []
  let removed = 0
  for (const condition of conditions) {
    const field = fieldOf(fields, condition.field)
    if (field === undefined || field.query === false) {
      removed += 1
      continue
    }
    if (
      field.options !== undefined &&
      field.options.length > 0 &&
      (condition.operator === 'eq' || condition.operator === 'in')
    ) {
      const candidates = Array.isArray(condition.value) ? condition.value : [condition.value]
      const valid = candidates.every(
        (item) => field.options?.some((option) => String(option.value) === String(item)) === true,
      )
      if (!valid) {
        removed += 1
        continue
      }
    }
    kept.push(condition)
  }
  return { conditions: kept, removed }
}

/**
 * 条件区间 / 数值校验（返回错误文案，合法返回 `undefined`）。
 *
 * @param condition 条件。
 * @param field 字段声明。
 * @returns 错误文案。
 */
export function validateConditionRange(condition: FilterCondition, field: FilterField | undefined): string | undefined {
  const numeric = field === undefined ? false : field.type === 'number'
  if (isRangeOperator(condition.operator)) {
    const value = Array.isArray(condition.value) ? condition.value : []
    const [start, end] = value as [unknown, unknown]
    if (
      numeric &&
      ((start !== undefined && start !== '' && !Number.isFinite(Number(start))) ||
        (end !== undefined && end !== '' && !Number.isFinite(Number(end))))
    ) {
      return FILTER_NUMBER_INVALID_TEXT
    }
    if (!isBlank(start) && !isBlank(end)) {
      if (numeric) {
        if (Number(start) > Number(end)) {
          return FILTER_RANGE_INVALID_TEXT
        }
      } else if (String(start) > String(end)) {
        return FILTER_RANGE_INVALID_TEXT
      }
    }
    return undefined
  }
  if (numeric && !isBlank(condition.value) && !Number.isFinite(Number(condition.value))) {
    return FILTER_NUMBER_INVALID_TEXT
  }
  return undefined
}

/**
 * 改写条件值（保留字段与操作符）。
 *
 * @param condition 条件。
 * @param next 新值。
 * @returns 新条件。
 */
export function toConditionValue(condition: FilterCondition, next: unknown): FilterCondition {
  return { field: condition.field, operator: condition.operator, value: next }
}

/**
 * 方案作用域优先级（`user` > `tenant` > `platform`）。
 *
 * @param scope 作用域。
 * @returns 优先级数值。
 */
export function schemePriority(scope: QuerySchemeScope): number {
  const index = QUERY_SCHEME_SCOPES.indexOf(scope)
  return index < 0 ? 0 : QUERY_SCHEME_SCOPES.length - 1 - index
}

/**
 * 归一单条方案（脏值返回 `undefined`）。
 *
 * @param value 原始值。
 * @returns 方案条目。
 */
export function normalizeSchemeEntry(value: unknown): QuerySchemeEntry | undefined {
  if (value === null || typeof value !== 'object') {
    return undefined
  }
  const entry = value as Record<string, unknown>
  const name = typeof entry.name === 'string' ? entry.name.trim() : ''
  if (name === '') {
    return undefined
  }
  const scope = QUERY_SCHEME_SCOPES.includes(entry.scope as QuerySchemeScope)
    ? (entry.scope as QuerySchemeScope)
    : 'user'
  const target = QUERY_SCHEME_TARGETS.includes(entry.target as QuerySchemeTarget)
    ? (entry.target as QuerySchemeTarget)
    : QUERY_SCHEME_TARGET_BUSINESS
  return {
    id: typeof entry.id === 'string' ? entry.id : undefined,
    name,
    scope,
    ownerId: typeof entry.ownerId === 'string' ? entry.ownerId : undefined,
    target,
    dictType: typeof entry.dictType === 'string' ? entry.dictType : undefined,
    fieldKey: typeof entry.fieldKey === 'string' ? entry.fieldKey : undefined,
    providerKey: typeof entry.providerKey === 'string' ? entry.providerKey : undefined,
    conditions: normalizeConditions(entry.conditions),
    params:
      entry.params !== null && typeof entry.params === 'object' ? (entry.params as Record<string, unknown>) : undefined,
    layout:
      entry.layout !== null && typeof entry.layout === 'object' ? (entry.layout as Record<string, unknown>) : undefined,
    isDefault: entry.isDefault === true,
    shared: entry.shared === true,
    status: typeof entry.status === 'string' ? entry.status : undefined,
  }
}

/**
 * 归一方案清单（脏项剔除）。
 *
 * @param value 原始值。
 * @returns 方案清单。
 */
export function normalizeSchemes(value: unknown): QuerySchemeEntry[] {
  if (!Array.isArray(value)) {
    return []
  }
  const result: QuerySchemeEntry[] = []
  for (const item of value) {
    const entry = normalizeSchemeEntry(item)
    if (entry !== undefined) {
      result.push(entry)
    }
  }
  return result
}

/**
 * 按名取方案。
 *
 * @param schemes 方案清单。
 * @param name 方案名。
 * @returns 方案条目。
 */
export function resolveScheme(schemes: readonly QuerySchemeEntry[], name: string): QuerySchemeEntry | undefined {
  return schemes.find((scheme) => scheme.name === name)
}

/**
 * 解析默认方案（取优先级最高且标记默认者）。
 *
 * @param schemes 方案清单。
 * @returns 方案条目。
 */
export function resolveDefaultScheme(schemes: readonly QuerySchemeEntry[]): QuerySchemeEntry | undefined {
  const candidates = schemes.filter((scheme) => scheme.isDefault === true)
  if (candidates.length === 0) {
    return undefined
  }
  return candidates.reduce((best, current) =>
    schemePriority(current.scope) > schemePriority(best.scope) ? current : best,
  )
}

/**
 * 是否已存在同名方案。
 *
 * @param schemes 方案清单。
 * @param name 方案名。
 * @returns 是否存在。
 */
export function hasSchemeName(schemes: readonly QuerySchemeEntry[], name: string): boolean {
  return schemes.some((scheme) => scheme.name === name)
}
