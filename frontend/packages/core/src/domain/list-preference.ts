/**
 * 领域纯函数：列表偏好（键 `list.{form_key}` / 结构归一 / 列偏好双向映射 / 失效剔除 / 体积保护）。
 *
 * 结构与后端列表偏好契约一致（`columns` / `page_size` / `density` / `query`）；
 * 不触 DOM、不请求、不读写存储（读写归件层经偏好持久化能力）。
 */

import { normalizeConditions, pruneConditions, type FilterCondition, type FilterField } from './filter'
import { PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, type TableColumn, type TableColumnState, type TableDensity } from './table'

/** 列表偏好键前缀（域）。 */
export const LIST_PREF_KEY_PREFIX = 'list'

/** 密度取值（与后端列表偏好契约同源）。 */
export type ListDensity = TableDensity

/** 密度取值集合。 */
export const LIST_DENSITIES: readonly ListDensity[] = ['default', 'small']

/** 单键体积上限（字节）。 */
export const LIST_PREF_MAX_BYTES = 65_536

/** 裁剪时保留的条件数上限。 */
export const LIST_PREF_MAX_CONDITIONS = 8

/** 列偏好（与后端列表偏好契约同形）。 */
export interface ListColumnPreference {
  /** 列键。 */
  prop: string
  /** 是否可见。 */
  visible: boolean
  /** 顺序（自 0 起）。 */
  order: number
  /** 宽度。 */
  width?: number
}

/** 条件偏好子键。 */
export interface ListQueryPreference {
  /** 关键字。 */
  keyword?: string
  /** 条件清单（条件模型，非序列化参数）。 */
  conditions: FilterCondition[]
}

/** 列表偏好（与后端列表偏好契约同形）。 */
export interface ListPreference {
  /** 列偏好。 */
  columns: ListColumnPreference[]
  /** 每页条数。 */
  page_size: number
  /** 密度。 */
  density: ListDensity
  /** 条件偏好。 */
  query: ListQueryPreference
}

/** 失效剔除结果。 */
export interface ListPreferencePruneResult {
  /** 剔除后的偏好。 */
  preference: ListPreference
  /** 剔除的条件数。 */
  removedConditions: number
  /** 剔除的列数。 */
  removedColumns: number
}

/** 页长夹取。 */
function clampPageSize(size: unknown): number {
  const value = Number(size)
  if (!Number.isFinite(value)) {
    return PAGE_SIZE_DEFAULT
  }
  return Math.min(PAGE_SIZE_MAX, Math.max(1, Math.trunc(value)))
}

/**
 * 列表偏好键（`list.{form_key}`）。
 *
 * @param formKey 表单 / 列表页标识。
 * @returns 偏好键。
 */
export function buildListPrefKey(formKey: string): string {
  const key = formKey.trim()
  return key === '' ? LIST_PREF_KEY_PREFIX : `${LIST_PREF_KEY_PREFIX}.${key}`
}

/**
 * 空列表偏好（缺省结构）。
 *
 * @returns 列表偏好。
 */
export function emptyListPreference(): ListPreference {
  return { columns: [], page_size: PAGE_SIZE_DEFAULT, density: 'default', query: { conditions: [] } }
}

/**
 * 归一列表偏好（脏值回落缺省；列偏好按 `prop` 去重保序）。
 *
 * @param value 原始值。
 * @returns 列表偏好。
 */
export function normalizeListPreference(value: unknown): ListPreference {
  if (value === null || typeof value !== 'object') {
    return emptyListPreference()
  }
  const entry = value as Record<string, unknown>
  const rawColumns = Array.isArray(entry.columns) ? entry.columns : []
  const seen = new Set<string>()
  const columns: ListColumnPreference[] = []
  for (const item of rawColumns) {
    if (item === null || typeof item !== 'object') {
      continue
    }
    const column = item as Record<string, unknown>
    const prop = typeof column.prop === 'string' ? column.prop.trim() : ''
    if (prop === '' || seen.has(prop)) {
      continue
    }
    seen.add(prop)
    columns.push({
      prop,
      visible: column.visible !== false,
      order: Number.isFinite(Number(column.order)) ? Math.max(0, Math.trunc(Number(column.order))) : columns.length,
      width: Number.isFinite(Number(column.width)) ? Math.trunc(Number(column.width)) : undefined,
    })
  }
  const rawQuery =
    entry.query !== null && typeof entry.query === 'object' ? (entry.query as Record<string, unknown>) : {}
  const keyword = typeof rawQuery.keyword === 'string' && rawQuery.keyword !== '' ? rawQuery.keyword : undefined
  const density = LIST_DENSITIES.includes(entry.density as ListDensity) ? (entry.density as ListDensity) : 'default'
  return {
    columns: columns.sort((left, right) => left.order - right.order),
    page_size: clampPageSize(entry.page_size),
    density,
    query: { keyword, conditions: normalizeConditions(rawQuery.conditions) },
  }
}

/**
 * 列状态 → 偏好列。
 *
 * @param states 列状态。
 * @returns 偏好列。
 */
export function toColumnPreferences(states: readonly TableColumnState[]): ListColumnPreference[] {
  return states.map((state, index) => ({
    prop: state.key,
    visible: state.visible,
    order: Number.isFinite(state.order) ? state.order : index,
    width: state.width,
  }))
}

/**
 * 偏好列 → 列状态（偏好中不存在于声明列的项剔除；声明列缺失项按声明默认追加）。
 *
 * @param prefs 偏好列。
 * @param columns 列声明。
 * @returns 列状态（顺序已按偏好重排）。
 */
export function fromColumnPreferences(
  prefs: readonly ListColumnPreference[],
  columns: readonly TableColumn[],
): TableColumnState[] {
  const byKey = new Map(prefs.map((pref) => [pref.prop, pref]))
  const withPref = columns
    .filter((column) => byKey.has(column.key))
    .sort((left, right) => (byKey.get(left.key)?.order ?? 0) - (byKey.get(right.key)?.order ?? 0))
  const withoutPref = columns.filter((column) => !byKey.has(column.key))
  return [...withPref, ...withoutPref].map((column, index) => {
    const pref = byKey.get(column.key)
    return {
      key: column.key,
      visible: pref?.visible ?? column.visible !== false,
      order: index,
      width: pref?.width ?? column.width,
    }
  })
}

/**
 * 写入条件偏好子键。
 *
 * @param preference 列表偏好。
 * @param conditions 条件清单。
 * @param keyword 关键字。
 * @returns 新列表偏好。
 */
export function withQuery(
  preference: ListPreference,
  conditions: readonly FilterCondition[],
  keyword?: string,
): ListPreference {
  return {
    ...preference,
    query: { keyword: keyword === '' ? undefined : keyword, conditions: conditions.map((item) => ({ ...item })) },
  }
}

/**
 * 清除条件偏好子键（「重置」语义）。
 *
 * @param preference 列表偏好。
 * @returns 新列表偏好。
 */
export function withoutQuery(preference: ListPreference): ListPreference {
  return { ...preference, query: { conditions: [] } }
}

/**
 * 失效剔除（条件按字段元数据、列按声明列表）。
 *
 * @param preference 列表偏好。
 * @param fields 查询类字段清单。
 * @param columns 列声明。
 * @returns 剔除结果与计数。
 */
export function pruneListPreference(
  preference: ListPreference,
  fields: readonly FilterField[],
  columns: readonly TableColumn[],
): ListPreferencePruneResult {
  const pruned = pruneConditions(preference.query.conditions, fields)
  const columnKeys = new Set(columns.map((column) => column.key))
  const keptColumns = preference.columns.filter((column) => columnKeys.has(column.prop))
  return {
    preference: {
      ...preference,
      columns: keptColumns,
      query: { keyword: preference.query.keyword, conditions: pruned.conditions },
    },
    removedConditions: pruned.removed,
    removedColumns: preference.columns.length - keptColumns.length,
  }
}

/**
 * 偏好体积（UTF-8 字节估算）。
 *
 * @param preference 列表偏好。
 * @returns 字节数。
 */
export function listPreferenceBytes(preference: ListPreference): number {
  return new TextEncoder().encode(JSON.stringify(preference)).length
}

/**
 * 是否超单键体积上限。
 *
 * @param preference 列表偏好。
 * @returns 是否超限。
 */
export function isListPreferenceOversized(preference: ListPreference): boolean {
  return listPreferenceBytes(preference) > LIST_PREF_MAX_BYTES
}

/**
 * 超限裁剪（先剔不可见列，再截断条件数）。
 *
 * @param preference 列表偏好。
 * @returns 裁剪后的偏好（未超限时原样返回）。
 */
export function trimListPreference(preference: ListPreference): ListPreference {
  if (!isListPreferenceOversized(preference)) {
    return preference
  }
  const trimmedColumns: ListPreference = {
    ...preference,
    columns: preference.columns.filter((column) => column.visible),
  }
  if (!isListPreferenceOversized(trimmedColumns)) {
    return trimmedColumns
  }
  if (trimmedColumns.query.conditions.length <= LIST_PREF_MAX_CONDITIONS) {
    return trimmedColumns
  }
  return {
    ...trimmedColumns,
    query: { ...trimmedColumns.query, conditions: trimmedColumns.query.conditions.slice(0, LIST_PREF_MAX_CONDITIONS) },
  }
}
