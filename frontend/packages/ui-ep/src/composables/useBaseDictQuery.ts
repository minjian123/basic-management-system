/** 字典高级查询投影：把核心高级查询编排基类 `BaseDictQuery` 投影为组合式（元数据 / 条件 / 执行 / 方案）。 */

import {
  BaseDictQuery,
  type DictAdvQueryResult,
  type DictAttrFieldOption,
  type DictAttrSchema,
  type DictConditionGroup,
  type DictItem,
  type DictQueryProvider,
  type DictQueryScheme,
  type DictSourceAdapter,
  type DictTarget,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体高级查询编排（可实例化）。 */
class DictQueryState extends BaseDictQuery {}

/** `useBaseDictQuery` 选项。 */
export interface UseBaseDictQueryOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 字典类型码。 */
  dictType?: string
  /** 目标（缺省取项）。 */
  target?: DictTarget
  /** 数据源（未注入即占位零请求）。 */
  source?: DictSourceAdapter
  /** 页长（缺省 20）。 */
  pageSize?: number
}

/** `useBaseDictQuery` 返回面（与核心方法一一对应的响应式面）。 */
export interface UseBaseDictQueryResult {
  /** 编排实例。 */
  query: BaseDictQuery
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 请求计数。 */
  requestCount: Ref<number>
  /** 字典类型（响应式）。 */
  dictType: Ref<string>
  /** 目标（响应式）。 */
  target: Ref<DictTarget>
  /** 属性 schema（响应式）。 */
  attrs: Ref<DictAttrSchema[]>
  /** 提供者清单（响应式）。 */
  providers: Ref<DictQueryProvider[]>
  /** 条件组（响应式）。 */
  conditions: Ref<DictConditionGroup>
  /** 提供者键（响应式）。 */
  providerKey: Ref<string>
  /** 提供者参数（响应式）。 */
  providerParams: Ref<Record<string, unknown>>
  /** 方案清单（响应式）。 */
  schemes: Ref<DictQueryScheme[]>
  /** 取项结果（响应式）。 */
  results: Ref<DictItem[]>
  /** 业务筛选行（响应式）。 */
  rows: Ref<Record<string, unknown>[]>
  /** 命中总数（响应式）。 */
  total: Ref<number>
  /** 页码（响应式）。 */
  page: Ref<number>
  /** 页长（响应式）。 */
  pageSize: Ref<number>
  /** 加载态（响应式）。 */
  loading: Ref<boolean>
  /** 是否错误态（响应式）。 */
  error: ComputedRef<boolean>
  /** 错误文案（响应式）。 */
  errorText: ComputedRef<string>
  /** 是否空态（响应式）。 */
  empty: ComputedRef<boolean>
  /** 元数据是否已加载（响应式）。 */
  metaLoaded: ComputedRef<boolean>
  /** 条件字段项（响应式）。 */
  fieldOptions: ComputedRef<DictAttrFieldOption[]>
  /** 注入 / 移除数据源。 */
  setSource(source: DictSourceAdapter | undefined): void
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 切换字典类型。 */
  setDictType(dictType: string): void
  /** 切换目标。 */
  setTarget(target: DictTarget): void
  /** 设置条件组。 */
  setConditions(group: DictConditionGroup): void
  /** 设置提供者与参数。 */
  setProvider(key: string, params?: Record<string, unknown>): void
  /** 设置页码。 */
  setPage(page: number): void
  /** 设置页长。 */
  setPageSize(size: number): void
  /** 加载元数据（属性 + 提供者）。 */
  loadMeta(): Promise<void>
  /** 执行查询。 */
  run(): Promise<void>
  /** 重置条件 / 提供者 / 结果。 */
  reset(): void
  /** 加载方案清单。 */
  loadSchemes(): Promise<void>
  /** 解析默认方案。 */
  resolveDefaultScheme(): Promise<void>
  /** 应用方案。 */
  applyScheme(scheme: DictQueryScheme): void
  /** 保存方案。 */
  saveScheme(name: string, scope?: DictQueryScheme['scope'], shared?: boolean): Promise<void>
  /** 删除方案。 */
  deleteScheme(schemeId: number): Promise<void>
  /** 业务筛选参数（宿主消费）。 */
  toBusinessFilter(): Record<string, unknown>
  /** 取项选中值（宿主回填字段）。 */
  selectedValues(): string[]
  /** 失效（清结果）。 */
  invalidate(): void
}

/**
 * 使用字典高级查询投影。
 *
 * @param options 选项。
 * @returns 编排实例与响应式面。
 */
export function useBaseDictQuery(options: UseBaseDictQueryOptions = {}): UseBaseDictQueryResult {
  const query = new DictQueryState()
  if (options.ready !== undefined) {
    query.setReady(options.ready)
  }
  if (options.dictType !== undefined) {
    query.setDictType(options.dictType)
  }
  if (options.target !== undefined) {
    query.setTarget(options.target)
  }
  if (options.pageSize !== undefined) {
    query.setPageSize(options.pageSize)
  }
  if (options.source !== undefined) {
    query.setSource(options.source)
  }

  const ready = ref(query.ready)
  const degraded = ref(query.degraded)
  const requestCount = ref(query.requestCount)
  const dictType = ref(query.dictType)
  const target = ref<DictTarget>(query.target)
  const attrs = ref<DictAttrSchema[]>([...query.attrs])
  const providers = ref<DictQueryProvider[]>([...query.providers])
  const conditions = ref<DictConditionGroup>(query.conditions)
  const providerKey = ref(query.providerKey)
  const providerParams = ref<Record<string, unknown>>({ ...query.providerParams })
  const schemes = ref<DictQueryScheme[]>([...query.schemes])
  const results = ref<DictItem[]>([...query.results])
  const rows = ref<Record<string, unknown>[]>([...query.rows])
  const total = ref(query.total)
  const page = ref(query.page)
  const pageSize = ref(query.pageSize)
  const loading = ref(query.loading)
  const errorCode = ref(query.errorCode)
  const errorMessage = ref(query.errorMessage)

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    ready.value = query.ready
    degraded.value = query.degraded
    requestCount.value = query.requestCount
    dictType.value = query.dictType
    target.value = query.target
    attrs.value = [...query.attrs]
    providers.value = [...query.providers]
    conditions.value = query.conditions
    providerKey.value = query.providerKey
    providerParams.value = { ...query.providerParams }
    schemes.value = [...query.schemes]
    results.value = [...query.results]
    rows.value = [...query.rows]
    total.value = query.total
    page.value = query.page
    pageSize.value = query.pageSize
    loading.value = query.loading
    errorCode.value = query.errorCode
    errorMessage.value = query.errorMessage
  }

  const off = query.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    query.dispose()
  })

  const error = computed(() => errorCode.value !== undefined)
  const errorText = computed(() => errorMessage.value)
  const empty = computed(() => !loading.value && errorCode.value === undefined && results.value.length === 0 && rows.value.length === 0)
  const metaLoaded = computed(() => attrs.value.length > 0 || providers.value.length > 0)
  const fieldOptions = computed(() => query.fieldOptions)

  return {
    query,
    ready,
    degraded,
    requestCount,
    dictType,
    target,
    attrs,
    providers,
    conditions,
    providerKey,
    providerParams,
    schemes,
    results,
    rows,
    total,
    page,
    pageSize,
    loading,
    error,
    errorText,
    empty,
    metaLoaded,
    fieldOptions,
    setSource: (next) => {
      query.setSource(next)
      sync()
    },
    setReady: (next) => {
      query.setReady(next)
      sync()
    },
    setDictType: (next) => {
      query.setDictType(next)
      sync()
    },
    setTarget: (next) => {
      query.setTarget(next)
      sync()
    },
    setConditions: (next) => {
      query.setConditions(next)
      sync()
    },
    setProvider: (key, params) => {
      query.setProvider(key, params)
      sync()
    },
    setPage: (next) => {
      query.setPage(next)
      sync()
    },
    setPageSize: (next) => {
      query.setPageSize(next)
      sync()
    },
    loadMeta: async () => {
      await query.loadMeta()
      sync()
    },
    run: async () => {
      await query.run()
      sync()
    },
    reset: () => {
      query.reset()
      sync()
    },
    loadSchemes: async () => {
      await query.loadSchemes()
      sync()
    },
    resolveDefaultScheme: async () => {
      await query.resolveDefaultScheme()
      sync()
    },
    applyScheme: (scheme) => {
      query.applyScheme(scheme)
      sync()
    },
    saveScheme: async (name, scope, shared) => {
      await query.saveScheme(name, scope, shared ?? false)
      sync()
    },
    deleteScheme: async (schemeId) => {
      await query.deleteScheme(schemeId)
      sync()
    },
    toBusinessFilter: () => query.toBusinessFilter(),
    selectedValues: () => query.selectedValues(),
    invalidate: () => {
      query.invalidate()
      sync()
    },
  }
}

/** 高级查询结果类型（导出供件层复用）。 */
export type { DictAdvQueryResult }
