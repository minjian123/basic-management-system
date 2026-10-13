/**
 * 领域纯函数：通用页面路由（清单归一 / 表单页声明 / 页面解析 / 联动键）。
 *
 * 后端清单响应与结果形状同源（`snake_case` 兼容归一；列表兼容裸数组与 `{items:[...]}` 包装）；
 * 框架无关、不触 DOM、不请求，同输入同输出。
 * 表单标识（`form_key`）面向界面；数据源标识（`data_source_key`）面向数据（多对一）。
 */

import { buildListPrefKey } from './list-preference'

/** 数据源类型（与后端 `DataSourceKind` 同源；预留其它取值）。 */
export const DATA_SOURCE_KINDS: readonly string[] = ['dict', 'form']
/** 表单标识类型（与后端 `FormKind` 同源）。 */
export const FORM_KINDS: readonly string[] = ['dict', 'form']
/** 字典类型取值（数据形态 = 字典；与后端 `FormKind.DICT` / `DataSourceKind.DICT` 同源）。 */
export const DICT_KIND = 'dict'
/** 标识格式（与后端 `FORM_KEY_PATTERN` / `DATA_SOURCE_KEY_PATTERN` 同源）。 */
export const PAGE_ROUTE_KEY_PATTERN = /^[a-z][a-z0-9_]*$/

/**
 * 是否字典（**唯一判定**：数据形态 = 字典）。
 *
 * 字典记录页据此套用《布局设计 · 字典页》骨架；后端同口径经清单响应 `is_dict` 下发。
 *
 * @param kind 类型取值（`dict` / `form`；未知 / 缺省按非字典）。
 * @returns 是否字典。
 */
export function isDictKind(kind: string | undefined): boolean {
  return kind === DICT_KIND
}

/** 数据源登记记录（`GET /api/v1/data-sources` 清单条目；兼容 `snake_case`）。 */
export interface DataSourceRecord {
  /** 数据源标识（业务码字符串）。 */
  dataSourceKey: string
  /** 名称。 */
  name: string
  /** 类型（`dict` / `form`，预留其它）。 */
  kind: string
  /** 是否字典（后端派生字段 `is_dict`；缺省按 `kind` 判定）。 */
  isDict: boolean
  /** 数据出口标识。 */
  dataSource: string
  /** 来源（`platform` / `product`）。 */
  origin: string
  /** 产品标识（`origin=product` 时非空）。 */
  productKey?: string
  /** 产品取数路径（`origin=product` 时前端经网关直取）。 */
  path?: string
  /** 数据权限可匹配字段白名单。 */
  allowlist: string[]
  /** 是否级联。 */
  cascade: boolean
  /** 可用策略集合。 */
  strategies: string[]
  /** 状态（`enabled` / `disabled`）。 */
  status: string
}

/** 表单标识登记记录（`GET /api/v1/form-keys` 清单条目；兼容 `snake_case`）。 */
export interface FormKeyRecord {
  /** 表单标识。 */
  formKey: string
  /** 名称。 */
  name: string
  /** 类型（`dict` / `form`）。 */
  kind: string
  /** 是否字典（后端派生字段 `is_dict`；缺省按 `kind` 判定）。 */
  isDict: boolean
  /** 物理表名。 */
  table: string
  /** 数据源标识（`form_key → data_source_key` 多对一；可空）。 */
  dataSourceKey?: string
  /** 状态（`enabled` / `disabled`）。 */
  status: string
}

/** 表单页声明（宿主登记：表单标识 → 页面）。 */
export interface FormPageDeclaration {
  /** 表单标识。 */
  formKey: string
  /** 页面标题。 */
  title: string
  /** 路由路径（须以 `/` 开头）。 */
  path: string
  /** 路由名（缺省取路径）。 */
  name?: string
  /** 路由元信息（标题 / 缓存等，透传宿主）。 */
  meta?: Record<string, unknown>
  /** 列表视图组件（异步加载器或组件对象）。 */
  list?: unknown
  /** 详情视图组件（异步加载器或组件对象）。 */
  detail?: unknown
  /** 数据源标识（显式覆盖；缺省取表单标识清单命中值）。 */
  dataSourceKey?: string
}

/** 页面解析结果。 */
export interface PageRouteResolution {
  /** 表单标识。 */
  formKey: string
  /** 页面标题。 */
  title: string
  /** 数据源标识。 */
  dataSourceKey: string
  /** 路由路径。 */
  path: string
  /** 路由名（缺省路径）。 */
  name: string
  /** 路由元信息。 */
  meta: Record<string, unknown>
  /** 列表视图组件。 */
  list?: unknown
  /** 详情视图组件。 */
  detail?: unknown
  /** 列表偏好键（`list.{form_key}`）。 */
  listPreferenceKey: string
  /** 查询方案表单标识（`field_key = form_key`）。 */
  schemeFieldKey: string
}

/**
 * 读字符串字段（兼容 `snake_case`；非串 / 空串回落缺省）。
 *
 * @param record 原始对象。
 * @param keys 候选键（依次尝试）。
 * @param fallback 缺省值。
 * @returns 字符串值。
 */
function readString(record: Record<string, unknown>, keys: readonly string[], fallback = ''): string {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'string' && value !== '') {
      return value
    }
  }
  return fallback
}

/**
 * 读字符串数组字段（兼容 `snake_case`；非数组回落空数组）。
 *
 * @param record 原始对象。
 * @param keys 候选键。
 * @returns 字符串数组。
 */
function readStringArray(record: Record<string, unknown>, keys: readonly string[]): string[] {
  for (const key of keys) {
    const value = record[key]
    if (Array.isArray(value)) {
      return value.filter((entry): entry is string => typeof entry === 'string')
    }
  }
  return []
}

/**
 * 读布尔字段（兼容 `snake_case`；非布尔回落 `undefined`）。
 *
 * @param record 原始对象。
 * @param keys 候选键（依次尝试）。
 * @returns 布尔值；未命中返回 `undefined`。
 */
function readBoolean(record: Record<string, unknown>, keys: readonly string[]): boolean | undefined {
  for (const key of keys) {
    const value = record[key]
    if (typeof value === 'boolean') {
      return value
    }
  }
  return undefined
}

/**
 * 归一单条数据源登记记录。
 *
 * @param raw 原始记录。
 * @returns 归一结果；非法（缺标识）返回 `undefined`。
 */
export function normalizeDataSourceRecord(raw: unknown): DataSourceRecord | undefined {
  if (raw === null || typeof raw !== 'object') {
    return undefined
  }
  const record = raw as Record<string, unknown>
  const dataSourceKey = readString(record, ['dataSourceKey', 'data_source_key'])
  if (dataSourceKey === '') {
    return undefined
  }
  const kind = readString(record, ['kind'])
  const productKey = readString(record, ['productKey', 'product_key'])
  const path = readString(record, ['path'])
  const result: DataSourceRecord = {
    dataSourceKey,
    name: readString(record, ['name'], dataSourceKey),
    kind,
    isDict: readBoolean(record, ['isDict', 'is_dict']) ?? isDictKind(kind),
    dataSource: readString(record, ['dataSource', 'data_source']),
    origin: readString(record, ['origin']),
    allowlist: readStringArray(record, ['allowlist']),
    cascade: record.cascade === true,
    strategies: readStringArray(record, ['strategies']),
    status: readString(record, ['status'], 'enabled'),
  }
  if (productKey !== '') {
    result.productKey = productKey
  }
  if (path !== '') {
    result.path = path
  }
  return result
}

/**
 * 归一数据源登记记录清单（兼容裸数组与 `{items:[...]}` 包装；脏项剔除）。
 *
 * @param raw 原始响应。
 * @returns 归一结果。
 */
export function normalizeDataSourceRecords(raw: unknown): DataSourceRecord[] {
  return normalizeRecordList(raw, normalizeDataSourceRecord)
}

/**
 * 归一单条表单标识登记记录。
 *
 * @param raw 原始记录。
 * @returns 归一结果；非法（缺标识）返回 `undefined`。
 */
export function normalizeFormKeyRecord(raw: unknown): FormKeyRecord | undefined {
  if (raw === null || typeof raw !== 'object') {
    return undefined
  }
  const record = raw as Record<string, unknown>
  const formKey = readString(record, ['formKey', 'form_key'])
  if (formKey === '') {
    return undefined
  }
  const kind = readString(record, ['kind'], DICT_KIND)
  const dataSourceKey = readString(record, ['dataSourceKey', 'data_source_key'])
  const result: FormKeyRecord = {
    formKey,
    name: readString(record, ['name'], formKey),
    kind,
    isDict: readBoolean(record, ['isDict', 'is_dict']) ?? isDictKind(kind),
    table: readString(record, ['table']),
    status: readString(record, ['status'], 'enabled'),
  }
  if (dataSourceKey !== '') {
    result.dataSourceKey = dataSourceKey
  }
  return result
}

/**
 * 归一表单标识登记记录清单（兼容裸数组与 `{items:[...]}` 包装；脏项剔除）。
 *
 * @param raw 原始响应。
 * @returns 归一结果。
 */
export function normalizeFormKeyRecords(raw: unknown): FormKeyRecord[] {
  return normalizeRecordList(raw, normalizeFormKeyRecord)
}

/**
 * 归一表单页声明。
 *
 * @param raw 原始声明。
 * @returns 归一结果；非法（标识 / 路径格式或标题缺失）返回 `undefined`。
 */
export function normalizeFormPageDeclaration(raw: unknown): FormPageDeclaration | undefined {
  if (raw === null || typeof raw !== 'object') {
    return undefined
  }
  const record = raw as Record<string, unknown>
  const formKey = readString(record, ['formKey', 'form_key'])
  const path = readString(record, ['path'])
  const title = readString(record, ['title'])
  if (!PAGE_ROUTE_KEY_PATTERN.test(formKey) || !path.startsWith('/') || title === '') {
    return undefined
  }
  const name = readString(record, ['name'])
  const dataSourceKey = readString(record, ['dataSourceKey', 'data_source_key'])
  const meta = record.meta !== null && typeof record.meta === 'object' && !Array.isArray(record.meta)
    ? { ...(record.meta as Record<string, unknown>) }
    : {}
  const result: FormPageDeclaration = { formKey, title, path, meta }
  if (name !== '') {
    result.name = name
  }
  if (record.list !== undefined) {
    result.list = record.list
  }
  if (record.detail !== undefined) {
    result.detail = record.detail
  }
  if (dataSourceKey !== '') {
    result.dataSourceKey = dataSourceKey
  }
  return result
}

/**
 * 解析页面（表单标识 → 页面：路由 + 视图 + 表单框架配置 + 数据源 + 联动键）。
 *
 * 数据源标识取值优先级：声明显式 `dataSourceKey` → 表单标识清单命中值；
 * **须落在数据源清单内**（未登记即视为不可用，返回 `undefined`）。
 *
 * @param declaration 表单页声明。
 * @param formKeys 表单标识清单。
 * @param dataSources 数据源清单。
 * @returns 解析结果；不可用返回 `undefined`。
 */
export function resolvePageRoute(
  declaration: FormPageDeclaration,
  formKeys: readonly FormKeyRecord[],
  dataSources: readonly DataSourceRecord[],
): PageRouteResolution | undefined {
  const record = formKeys.find((entry) => entry.formKey === declaration.formKey)
  const dataSourceKey = declaration.dataSourceKey ?? record?.dataSourceKey
  if (dataSourceKey === undefined || dataSourceKey === '') {
    return undefined
  }
  if (!dataSources.some((entry) => entry.dataSourceKey === dataSourceKey)) {
    return undefined
  }
  return {
    formKey: declaration.formKey,
    title: declaration.title,
    dataSourceKey,
    path: declaration.path,
    name: declaration.name ?? declaration.path,
    meta: { ...(declaration.meta ?? {}) },
    list: declaration.list,
    detail: declaration.detail,
    listPreferenceKey: buildListPrefKey(declaration.formKey),
    schemeFieldKey: declaration.formKey,
  }
}

/**
 * 归一记录清单（兼容裸数组与 `{items:[...]}` 包装；逐项归一 + 脏项剔除 + 按首键去重保序）。
 *
 * @param raw 原始响应。
 * @param normalize 单条归一函数。
 * @returns 归一结果。
 */
function normalizeRecordList<T>(
  raw: unknown,
  normalize: (value: unknown) => T | undefined,
): T[] {
  const list = Array.isArray(raw)
    ? raw
    : raw !== null && typeof raw === 'object' && Array.isArray((raw as { items?: unknown }).items)
      ? ((raw as { items: unknown[] }).items)
      : []
  const result: T[] = []
  for (const entry of list) {
    const item = normalize(entry)
    if (item !== undefined) {
      result.push(item)
    }
  }
  return result
}
