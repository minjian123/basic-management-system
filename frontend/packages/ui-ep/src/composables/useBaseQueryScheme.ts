/** 查询方案投影：把核心查询方案组件基类 `BaseQueryScheme` 投影为组合式（条件 / 方案 CRUD / 摘要 / 查询参数）。 */

import {
  BaseQueryScheme,
  buildQueryParams,
  resolveDefaultScheme,
  summarizeConditions,
  type ConditionSummary,
  type FilterCondition,
  type FilterField,
  type QuerySchemeEntry,
  type QuerySchemeScope,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体查询方案件（可实例化）。 */
class Scheme extends BaseQueryScheme {}

/** 选项。 */
export interface UseBaseQuerySchemeOptions {
  /** 查询类字段声明（摘要与失效剔除用）。 */
  fields?: FilterField[]
  /** 默认条件种子。 */
  defaults?: FilterCondition[]
  /** 初始条件。 */
  conditions?: FilterCondition[]
  /** 初始关键字。 */
  keyword?: string
  /** 初始方案清单。 */
  schemes?: QuerySchemeEntry[]
}

/** `useBaseQueryScheme` 返回面。 */
export interface UseBaseQuerySchemeResult {
  /** 查询方案基类实例。 */
  scheme: BaseQueryScheme
  /** 当前条件。 */
  conditions: Ref<FilterCondition[]>
  /** 当前关键字。 */
  keyword: Ref<string>
  /** 已保存方案。 */
  schemes: Ref<QuerySchemeEntry[]>
  /** 当前应用方案名。 */
  activeScheme: Ref<string | undefined>
  /** 默认方案名。 */
  defaultSchemeName: Ref<string | undefined>
  /** 条件摘要（仅已生效条件）。 */
  summaries: ComputedRef<ConditionSummary[]>
  /** 取数查询参数。 */
  queryParams: ComputedRef<Record<string, unknown>>
  /** 设置条件。 */
  setConditions: (conditions: readonly FilterCondition[]) => void
  /** 设置关键字。 */
  setKeyword: (value: string) => void
  /** 重置条件（回默认种子）。 */
  resetConditions: () => void
  /** 设置默认条件种子。 */
  setDefaults: (conditions: readonly FilterCondition[]) => void
  /** 按字段声明剔除失效条件（返回剔除数）。 */
  prune: () => number
  /** 保存方案（同名覆盖）。 */
  saveScheme: (name: string, scope?: QuerySchemeScope, isDefault?: boolean) => void
  /** 应用方案（返回条件副本；未命中返回 `undefined`）。 */
  applyScheme: (name: string) => FilterCondition[] | undefined
  /** 删除方案。 */
  removeScheme: (name: string) => boolean
  /** 重命名方案。 */
  renameScheme: (oldName: string, newName: string) => boolean
  /** 设默认方案。 */
  setDefaultScheme: (name: string | undefined) => void
  /** 整体回写方案清单（远端归一形态）。 */
  setSchemes: (schemes: readonly QuerySchemeEntry[]) => void
}

/**
 * 使用查询方案投影。
 *
 * @param options 选项。
 * @returns 查询方案基类实例与响应式面。
 */
export function useBaseQueryScheme(options: UseBaseQuerySchemeOptions = {}): UseBaseQuerySchemeResult {
  const scheme = new Scheme()
  if (options.defaults !== undefined) {
    scheme.setDefaults(options.defaults)
  }
  if (options.conditions !== undefined) {
    scheme.setConditions(options.conditions)
  }
  if (options.keyword !== undefined) {
    scheme.setKeyword(options.keyword)
  }
  if (options.schemes !== undefined) {
    scheme.setSchemes(options.schemes)
  }

  const conditions = ref<FilterCondition[]>(scheme.conditions.map((item) => ({ ...item })))
  const keyword = ref(scheme.keyword)
  const schemes = ref<QuerySchemeEntry[]>([])
  const activeScheme = ref<string | undefined>(scheme.activeScheme)

  /** 方案内态 → 契约形态。 */
  const entries = (): QuerySchemeEntry[] =>
    scheme.schemes.map((item) => ({
      id: item.id,
      name: item.name,
      scope: item.scope ?? 'user',
      target: 'business' as const,
      conditions: item.conditions.map((condition) => ({ ...condition })),
      isDefault: item.isDefault === true,
      shared: item.shared === true,
      ownerId: item.ownerId,
    }))

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    conditions.value = scheme.conditions.map((item) => ({ ...item }))
    keyword.value = scheme.keyword
    schemes.value = entries()
    activeScheme.value = scheme.activeScheme
  }
  const off = scheme.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)
  sync()

  return {
    scheme,
    conditions,
    keyword,
    schemes,
    activeScheme,
    defaultSchemeName: computed(() => resolveDefaultScheme(schemes.value)?.name),
    summaries: computed(() => summarizeConditions(conditions.value, options.fields ?? [])),
    queryParams: computed(() => buildQueryParams(conditions.value, keyword.value)),
    setConditions: (next) => {
      scheme.setConditions(next)
      sync()
    },
    setKeyword: (value) => {
      scheme.setKeyword(value)
      sync()
    },
    resetConditions: () => {
      scheme.resetConditions()
      sync()
    },
    setDefaults: (next) => {
      scheme.setDefaults(next)
      sync()
    },
    prune: () => {
      const removed = scheme.prune(options.fields ?? [])
      sync()
      return removed
    },
    saveScheme: (name, scope, isDefault) => {
      scheme.saveScheme({
        name,
        scope,
        conditions: scheme.conditions.map((item) => ({ ...item })),
        isDefault,
      })
      scheme.activeScheme = name
      sync()
    },
    applyScheme: (name) => {
      const applied = scheme.applyScheme(name)
      sync()
      return applied
    },
    removeScheme: (name) => {
      const removed = scheme.removeScheme(name)
      sync()
      return removed
    },
    renameScheme: (oldName, newName) => {
      const renamed = scheme.renameScheme(oldName, newName)
      sync()
      return renamed
    },
    setDefaultScheme: (name) => {
      scheme.setDefaultScheme(name)
      sync()
    },
    setSchemes: (next) => {
      scheme.setSchemes(next)
      sync()
    },
  }
}
