/** 文案目录投影：把核心编排能力基类 `BaseMessageCatalog` 投影为组合式（清单 / 网格 / 筛选 / 保存 / 缓存失效）。 */

import {
  BaseMessageCatalog,
  type BaseAccess,
  type BaseLocale,
  type BaseNotice,
  type I18nCheckResult,
  type I18nFilter,
  type I18nLocaleInput,
  type I18nLocaleItem,
  type I18nMessageItem,
  type MessageJobs,
  type MessagePhase,
  type SaveResult,
} from '@bms/core'
import { markRaw, onScopeDispose, ref, toRaw, type Ref } from 'vue'

/** 具体文案目录件（可实例化）。 */
class MessageCatalogState extends BaseMessageCatalog {}

/** 选项。 */
export interface UseBaseMessageCatalogOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 业务标识（后端路径段）。 */
  biz?: string
  /** 业务中文名。 */
  bizName?: string
  /** 默认语言（不可停用）。 */
  defaultLocale?: string
  /** 初始页码。 */
  page?: number
  /** 每页行数。 */
  pageSize?: number
  /** 初始筛选条件。 */
  filter?: Partial<I18nFilter>
  /** 聚焦语言。 */
  activeLocale?: string
  /** 是否显示停用语言列。 */
  showDisabledLocales?: boolean
  /** 虚拟滚动阈值。 */
  virtualThreshold?: number
  /** 注入的处理函数集（未注入即占位）。 */
  jobs?: MessageJobs
  /** 语言上下文（组合；聚焦语言经其承载）。 */
  locale?: BaseLocale
  /** 权限上下文（未注入不校验）。 */
  access?: BaseAccess
  /** 提示通知协作者。 */
  notice?: BaseNotice
}

/** `useBaseMessageCatalog` 返回面。 */
export interface UseBaseMessageCatalogResult {
  /** 文案目录基类实例（跨实例经 `markRaw` 隔离）。 */
  catalog: BaseMessageCatalog
  /** 数据通路是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 是否进行中（响应式）。 */
  busy: Ref<boolean>
  /** 当前阶段（响应式）。 */
  phase: Ref<MessagePhase>
  /** 是否存在未保存变更（响应式）。 */
  dirty: Ref<boolean>
  /** 语言清单（响应式）。 */
  locales: Ref<I18nLocaleItem[]>
  /** 语言列集（响应式）。 */
  columns: Ref<I18nLocaleItem[]>
  /** 当前页文案行（响应式）。 */
  messages: Ref<I18nMessageItem[]>
  /** 按筛选条件本地过滤后的可见行（响应式）。 */
  visibleMessages: Ref<I18nMessageItem[]>
  /** 已修改行的键（响应式）。 */
  modifiedKeys: Ref<string[]>
  /** 存在缺失翻译的启用语言（响应式）。 */
  missingCodes: Ref<string[]>
  /** 总条数（响应式）。 */
  total: Ref<number>
  /** 当前页码（响应式）。 */
  page: Ref<number>
  /** 总页数（响应式）。 */
  pageCount: Ref<number>
  /** 每页行数（响应式）。 */
  pageSize: Ref<number>
  /** 筛选条件（响应式）。 */
  filter: Ref<I18nFilter>
  /** 聚焦语言（响应式）。 */
  activeLocale: Ref<string>
  /** 是否显示停用语言列（响应式）。 */
  showDisabledLocales: Ref<boolean>
  /** 是否切换虚拟滚动（响应式）。 */
  virtualized: Ref<boolean>
  /** 内容派生幂等键（响应式）。 */
  idempotencyKey: Ref<string>
  /** 是否可保存（响应式）。 */
  canSave: Ref<boolean>
  /** 提示 / 失败文案（响应式）。 */
  errorMessage: Ref<string>
  /** 最近错误码（响应式）。 */
  errorCode: Ref<number>
  /** 语言包版本号（响应式）。 */
  messagesRevision: Ref<number>
  /** 下发后端的筛选参数（响应式）。 */
  exportParams: Ref<Record<string, unknown>>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入处理函数集（整体替换）。 */
  setJobs: (jobs: MessageJobs) => void
  /** 更新筛选条件。 */
  setFilter: (filter: Partial<I18nFilter>) => void
  /** 设置聚焦语言。 */
  setActiveLocale: (code: string) => void
  /** 切换停用语言列显隐。 */
  setShowDisabledLocales: (value: boolean) => void
  /** 设置虚拟滚动阈值。 */
  setVirtualThreshold: (value: number) => void
  /** 切换页码。 */
  setPage: (page: number) => void
  /** 设置每页行数。 */
  setPageSize: (size: number) => void
  /** 取数。 */
  load: () => Promise<boolean>
  /** 保留筛选与页码重取。 */
  reload: () => Promise<boolean>
  /** 编辑单元格。 */
  editCell: (input: { key: string; locale: string; value: string }) => boolean
  /** 新增 key。 */
  addKey: (input: { key: string; values?: Record<string, string> }) => boolean
  /** 删除 key。 */
  removeKey: (key: string) => boolean
  /** 新增语言。 */
  addLocale: (input: I18nLocaleInput) => I18nCheckResult
  /** 修改语言。 */
  updateLocale: (code: string, patch: I18nLocaleInput) => I18nCheckResult
  /** 启停语言。 */
  toggleLocale: (code: string, enabled: boolean) => I18nCheckResult
  /** 删除语言。 */
  removeLocale: (code: string) => I18nCheckResult
  /** 批量保存。 */
  save: () => Promise<SaveResult | undefined>
  /** 重试失败保存。 */
  retry: () => Promise<SaveResult | undefined>
  /** 缓存主动失效。 */
  invalidateCache: () => Promise<boolean>
  /** 语言包重载。 */
  reloadMessages: () => Promise<boolean>
  /** 撤销未保存变更。 */
  resetDirty: () => void
  /** 整体复位。 */
  reset: () => void
  /** 是否具备权限码。 */
  isAllowed: (perm: string) => boolean
}

/**
 * 使用文案目录投影。
 *
 * @param options 选项。
 * @returns 文案目录基类实例与响应式面。
 */
export function useBaseMessageCatalog(options: UseBaseMessageCatalogOptions = {}): UseBaseMessageCatalogResult {
  const catalog = new MessageCatalogState()
  if (options.biz !== undefined) {
    catalog.biz = options.biz
  }
  if (options.bizName !== undefined) {
    catalog.bizName = options.bizName
  }
  if (options.defaultLocale !== undefined) {
    catalog.defaultLocale = options.defaultLocale
  }
  if (options.page !== undefined) {
    catalog.page = Math.max(1, options.page)
  }
  if (options.pageSize !== undefined) {
    catalog.pageSize = Math.max(1, options.pageSize)
  }
  if (options.filter !== undefined) {
    catalog.filter = { ...catalog.filter, ...options.filter }
  }
  if (options.virtualThreshold !== undefined) {
    catalog.virtualThreshold = options.virtualThreshold
  }
  if (options.locale !== undefined) {
    catalog.localeContext = markRaw(toRaw(options.locale))
  }
  if (options.jobs !== undefined) {
    catalog.jobs = options.jobs
  }
  if (options.access !== undefined) {
    catalog.access = markRaw(toRaw(options.access))
  }
  if (options.notice !== undefined) {
    catalog.notice = markRaw(toRaw(options.notice))
  }
  catalog.setShowDisabledLocales(options.showDisabledLocales ?? false)
  if (options.activeLocale !== undefined && options.activeLocale !== '') {
    catalog.setActiveLocale(options.activeLocale)
  } else {
    catalog.activeLocale = ''
  }
  catalog.setReady(options.ready ?? false)

  const ready = ref(catalog.ready)
  const degraded = ref(catalog.degraded)
  const busy = ref(catalog.busy)
  const phase = ref<MessagePhase>(catalog.phase)
  const dirty = ref(catalog.dirty)
  const locales = ref<I18nLocaleItem[]>(catalog.locales)
  const columns = ref<I18nLocaleItem[]>(catalog.columns)
  const messages = ref<I18nMessageItem[]>(catalog.messages)
  const visibleMessages = ref<I18nMessageItem[]>(catalog.visibleMessages)
  const modifiedKeys = ref<string[]>(catalog.modifiedKeys)
  const missingCodes = ref<string[]>(catalog.missingCodes)
  const total = ref(catalog.total)
  const page = ref(catalog.page)
  const pageCount = ref(catalog.pageCount)
  const pageSize = ref(catalog.pageSize)
  const filter = ref<I18nFilter>({ ...catalog.filter })
  const activeLocale = ref(catalog.activeLocale)
  const showDisabledLocales = ref(catalog.showDisabledLocales)
  const virtualized = ref(catalog.virtualized)
  const idempotencyKey = ref(catalog.idempotencyKey)
  const canSave = ref(catalog.canSave)
  const errorMessage = ref(catalog.errorMessage)
  const errorCode = ref(catalog.errorCode)
  const messagesRevision = ref(catalog.messagesRevision)
  const exportParams = ref<Record<string, unknown>>(catalog.exportParams)

  /** 从基类实例同步响应式面（集合一律重建，核心集合非响应式）。 */
  const sync = (): void => {
    ready.value = catalog.ready
    degraded.value = catalog.degraded
    busy.value = catalog.busy
    phase.value = catalog.phase
    dirty.value = catalog.dirty
    locales.value = catalog.locales.map((item) => ({ ...item }))
    columns.value = catalog.columns.map((item) => ({ ...item }))
    messages.value = catalog.messages.map((row) => ({
      key: row.key,
      values: { ...row.values },
      missing: [...row.missing],
    }))
    visibleMessages.value = catalog.visibleMessages.map((row) => ({
      key: row.key,
      values: { ...row.values },
      missing: [...row.missing],
    }))
    modifiedKeys.value = catalog.modifiedKeys
    missingCodes.value = catalog.missingCodes
    total.value = catalog.total
    page.value = catalog.page
    pageCount.value = catalog.pageCount
    pageSize.value = catalog.pageSize
    filter.value = { ...catalog.filter }
    activeLocale.value = catalog.activeLocale
    showDisabledLocales.value = catalog.showDisabledLocales
    virtualized.value = catalog.virtualized
    idempotencyKey.value = catalog.idempotencyKey
    canSave.value = catalog.canSave
    errorMessage.value = catalog.errorMessage
    errorCode.value = catalog.errorCode
    messagesRevision.value = catalog.messagesRevision
    exportParams.value = catalog.exportParams
  }

  const off = catalog.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    catalog,
    ready,
    degraded,
    busy,
    phase,
    dirty,
    locales,
    columns,
    messages,
    visibleMessages,
    modifiedKeys,
    missingCodes,
    total,
    page,
    pageCount,
    pageSize,
    filter,
    activeLocale,
    showDisabledLocales,
    virtualized,
    idempotencyKey,
    canSave,
    errorMessage,
    errorCode,
    messagesRevision,
    exportParams,
    setReady: (value) => {
      catalog.setReady(value)
      sync()
    },
    setJobs: (jobs) => {
      catalog.setJobs(jobs)
      sync()
    },
    setFilter: (value) => {
      catalog.setFilter(value)
      sync()
    },
    setActiveLocale: (code) => {
      catalog.setActiveLocale(code)
      sync()
    },
    setShowDisabledLocales: (value) => {
      catalog.setShowDisabledLocales(value)
      sync()
    },
    setVirtualThreshold: (value) => {
      catalog.setVirtualThreshold(value)
      sync()
    },
    setPage: (value) => {
      catalog.setPage(value)
      sync()
    },
    setPageSize: (value) => {
      catalog.setPageSize(value)
      sync()
    },
    load: async () => {
      const value = await catalog.load()
      sync()
      return value
    },
    reload: async () => {
      const value = await catalog.reload()
      sync()
      return value
    },
    editCell: (input) => {
      const value = catalog.editCell(input)
      sync()
      return value
    },
    addKey: (input) => {
      const value = catalog.addKey(input)
      sync()
      return value
    },
    removeKey: (key) => {
      const value = catalog.removeKey(key)
      sync()
      return value
    },
    addLocale: (input) => {
      const value = catalog.addLocale(input)
      sync()
      return value
    },
    updateLocale: (code, patch) => {
      const value = catalog.updateLocale(code, patch)
      sync()
      return value
    },
    toggleLocale: (code, enabled) => {
      const value = catalog.toggleLocale(code, enabled)
      sync()
      return value
    },
    removeLocale: (code) => {
      const value = catalog.removeLocale(code)
      sync()
      return value
    },
    save: async () => {
      const value = await catalog.save()
      sync()
      return value
    },
    retry: async () => {
      const value = await catalog.retry()
      sync()
      return value
    },
    invalidateCache: async () => {
      const value = await catalog.invalidateCache()
      sync()
      return value
    },
    reloadMessages: async () => {
      const value = await catalog.reloadMessages()
      sync()
      return value
    },
    resetDirty: () => {
      catalog.resetDirty()
      sync()
    },
    reset: () => {
      catalog.reset()
      sync()
    },
    isAllowed: (perm) => catalog.isAllowed(perm),
  }
}
