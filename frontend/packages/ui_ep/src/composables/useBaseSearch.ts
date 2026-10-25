/** 搜索族组件基类投影：把核心 `BaseSearch` 投影为组合式（关键词 / 域 / 分组 / 建议 / 最近搜索 / 日志与文件检索）。 */

import {
  BaseAccess,
  BaseSearch,
  type SearchDegradeReason,
  type SearchDomain,
  type SearchEngineAdapter,
  type SearchGroup,
  type SearchHit,
  type SearchPhase,
  type SearchRange,
} from '@bms/core'
import { computed, markRaw, onScopeDispose, ref, toRaw, type ComputedRef, type Ref } from 'vue'

import { onGlobalKeydown } from '../utils/keyboard'
import { useBasePersistedState, type PersistedStorageOption } from './useBasePersistedState'

/** 缺省最近搜索存储键。 */
const DEFAULT_RECENT_KEY = 'bms_search_recent'

/** 具体搜索件（可实例化）。 */
class SearchState extends BaseSearch {}

/** 投影选项。 */
export interface UseBaseSearchOptions {
  /** 数据通路是否就绪（缺省 `false`）。 */
  ready?: boolean
  /** 初始关键词。 */
  keyword?: string
  /** 当前域。 */
  activeDomain?: string
  /** 可检索域（宿主传入，含权限码）。 */
  domains?: SearchDomain[]
  /** 初始分组结果。 */
  groups?: SearchGroup[]
  /** 页码。 */
  page?: number
  /** 页长。 */
  pageSize?: number
  /** 初始最近搜索。 */
  recentKeywords?: string[]
  /** 检索引擎（未注入即占位零请求）。 */
  engine?: SearchEngineAdapter
  /** 权限上下文（域二次过滤）。 */
  access?: BaseAccess
  /** 最近搜索存储后端（缺省 `local`）。 */
  storage?: PersistedStorageOption
  /** 最近搜索存储键（缺省 `bms_search_recent`）。 */
  storageKey?: string
}

/** `useBaseSearch` 返回面。 */
export interface UseBaseSearchResult {
  /** 搜索基类实例。 */
  state: BaseSearch
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 请求计数（响应式）。 */
  requestCount: Ref<number>
  /** 检索阶段（响应式）。 */
  phase: Ref<SearchPhase>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 关键词（响应式）。 */
  keyword: Ref<string>
  /** 当前域（响应式）。 */
  activeDomain: Ref<string>
  /** 可检索域（权限过滤后，响应式）。 */
  accessibleDomains: ComputedRef<SearchDomain[]>
  /** 分组结果（响应式）。 */
  groups: Ref<SearchGroup[]>
  /** 命中总数（响应式）。 */
  total: Ref<number>
  /** 页码（响应式）。 */
  page: Ref<number>
  /** 页长（响应式）。 */
  pageSize: Ref<number>
  /** 即时建议（响应式）。 */
  suggestions: Ref<SearchHit[]>
  /** 最近搜索（响应式）。 */
  recentKeywords: Ref<string[]>
  /** 审计日志命中（响应式）。 */
  logItems: Ref<SearchHit[]>
  /** 审计日志总数（响应式）。 */
  logTotal: Ref<number>
  /** 审计日志页码（响应式）。 */
  logPage: Ref<number>
  /** 审计日志页长（响应式）。 */
  logPageSize: Ref<number>
  /** 日志类型（响应式）。 */
  logType: Ref<string>
  /** 审计时间范围（响应式）。 */
  logRange: Ref<SearchRange>
  /** 文件内容命中（响应式）。 */
  fileItems: Ref<SearchHit[]>
  /** 文件内容总数（响应式）。 */
  fileTotal: Ref<number>
  /** 文件内容页码（响应式）。 */
  filePage: Ref<number>
  /** 文件内容页长（响应式）。 */
  filePageSize: Ref<number>
  /** 文件类型（响应式）。 */
  fileType: Ref<string>
  /** 检索侧降级标记（响应式）。 */
  engineDegraded: Ref<boolean>
  /** 降级原因（响应式）。 */
  degradeReason: Ref<SearchDegradeReason | undefined>
  /** 是否具备审计日志权限（响应式）。 */
  hasLogPermission: ComputedRef<boolean>
  /** 是否具备文件内容检索权限（响应式）。 */
  hasFilePermission: ComputedRef<boolean>
  /** 降级替代入口域（响应式）。 */
  fallbackDomains: ComputedRef<SearchDomain[]>
  /** 切换就绪态。 */
  setReady: (value: boolean) => void
  /** 注入 / 移除检索引擎。 */
  setEngine: (engine: SearchEngineAdapter | undefined) => void
  /** 注入 / 移除权限上下文。 */
  setAccess: (access: BaseAccess | undefined) => void
  /** 覆盖可检索域。 */
  setDomains: (domains: readonly SearchDomain[]) => void
  /** 设置关键词。 */
  setKeyword: (keyword: string) => void
  /** 设置当前域。 */
  setActiveDomain: (key: string) => void
  /** 设置页码。 */
  setPage: (page: number) => void
  /** 设置页长。 */
  setPageSize: (size: number) => void
  /** 设置审计时间范围。 */
  setLogRange: (range: SearchRange) => void
  /** 设置日志类型。 */
  setLogType: (type: string) => void
  /** 设置审计日志页码。 */
  setLogPage: (page: number) => void
  /** 设置审计日志页长。 */
  setLogPageSize: (size: number) => void
  /** 设置文件类型。 */
  setFileType: (type: string) => void
  /** 设置文件内容页码。 */
  setFilePage: (page: number) => void
  /** 设置文件内容页长。 */
  setFilePageSize: (size: number) => void
  /** 全局检索。 */
  search: () => Promise<SearchGroup[] | undefined>
  /** 即时建议。 */
  suggest: () => Promise<SearchHit[] | undefined>
  /** 清空建议。 */
  clearSuggestions: () => void
  /** 审计日志检索。 */
  searchLogs: () => Promise<SearchHit[] | undefined>
  /** 文件内容检索。 */
  searchFiles: () => Promise<SearchHit[] | undefined>
  /** 追加最近搜索。 */
  addRecentKeyword: (keyword: string) => void
  /** 移除最近搜索。 */
  removeRecentKeyword: (keyword: string) => void
  /** 清空最近搜索。 */
  clearRecentKeywords: () => void
  /** 注册全局快捷键（缺省 `mod+k`），返回取消函数。 */
  registerShortcut: (handler: () => void, shortcut?: string) => () => void
}

/**
 * 判断键盘事件是否匹配快捷键（`mod+k` / `alt+k` / `ctrl+shift+f` 等）。
 *
 * @param event 键盘事件。
 * @param shortcut 快捷键描述。
 * @returns 是否匹配。
 */
function matchesShortcut(event: KeyboardEvent, shortcut: string): boolean {
  const parts = shortcut
    .toLowerCase()
    .split('+')
    .map((part) => part.trim())
    .filter((part) => part !== '')
  const key = parts.filter((part) => !['mod', 'ctrl', 'control', 'meta', 'cmd', 'alt', 'shift'].includes(part)).at(-1)
  if (key === undefined || event.key.toLowerCase() !== key) {
    return false
  }
  const wantMod = parts.includes('mod')
  const wantCtrl = parts.includes('ctrl') || parts.includes('control')
  const wantMeta = parts.includes('meta') || parts.includes('cmd')
  const wantAlt = parts.includes('alt')
  const wantShift = parts.includes('shift')
  if (wantMod && !(event.ctrlKey || event.metaKey)) {
    return false
  }
  if (!wantMod && (wantCtrl || wantMeta) && !(event.ctrlKey || event.metaKey)) {
    return false
  }
  if (wantAlt !== event.altKey) {
    return false
  }
  if (wantShift !== event.shiftKey) {
    return false
  }
  return true
}

/**
 * 使用搜索族组件基类投影。
 *
 * @param options 选项。
 * @returns 搜索基类实例与响应式面。
 */
export function useBaseSearch(options: UseBaseSearchOptions = {}): UseBaseSearchResult {
  const search = new SearchState()
  const persisted = useBasePersistedState({
    stateKey: options.storageKey ?? DEFAULT_RECENT_KEY,
    storage: options.storage ?? 'local',
  })
  search.attachPersisted(persisted.persisted)
  if (options.recentKeywords !== undefined && options.recentKeywords.length > 0) {
    search.recentKeywords.splice(0, search.recentKeywords.length, ...options.recentKeywords)
  }
  if (options.domains !== undefined) {
    search.setDomains(options.domains)
  }
  if (options.groups !== undefined) {
    search.groups.splice(0, search.groups.length, ...options.groups)
  }
  if (options.keyword !== undefined) {
    search.setKeyword(options.keyword)
  }
  if (options.activeDomain !== undefined) {
    search.setActiveDomain(options.activeDomain)
  }
  if (options.page !== undefined) {
    search.setPage(options.page)
  }
  if (options.pageSize !== undefined) {
    search.setPageSize(options.pageSize)
  }
  if (options.engine !== undefined) {
    search.setEngine(markRaw(toRaw(options.engine)))
  }
  if (options.access !== undefined) {
    search.setAccess(markRaw(toRaw(options.access)))
  }
  search.setReady(options.ready ?? false)

  const ready = ref(search.ready)
  const degraded = ref(search.degraded)
  const requestCount = ref(search.requestCount)
  const phase = ref<SearchPhase>(search.phase)
  const errorMessage = ref(search.errorMessage)
  const keyword = ref(search.keyword)
  const activeDomain = ref(search.activeDomain)
  const groups = ref<SearchGroup[]>([...search.groups])
  const total = ref(search.total)
  const page = ref(search.page)
  const pageSize = ref(search.pageSize)
  const suggestions = ref<SearchHit[]>([...search.suggestions])
  const recentKeywords = ref<string[]>([...search.recentKeywords])
  const logItems = ref<SearchHit[]>([...search.logItems])
  const logTotal = ref(search.logTotal)
  const logPage = ref(search.logPage)
  const logPageSize = ref(search.logPageSize)
  const logType = ref(search.logType)
  const logRange = ref<SearchRange>({ ...search.logRange })
  const fileItems = ref<SearchHit[]>([...search.fileItems])
  const fileTotal = ref(search.fileTotal)
  const filePage = ref(search.filePage)
  const filePageSize = ref(search.filePageSize)
  const fileType = ref(search.fileType)
  const engineDegraded = ref(search.engineDegraded)
  const degradeReason = ref<SearchDegradeReason | undefined>(search.degradeReason)
  const accessibleDomains = computed(() => search.accessibleDomains)
  const hasLogPermission = computed(() => search.hasLogPermission)
  const hasFilePermission = computed(() => search.hasFilePermission)
  const fallbackDomains = computed(() => search.fallbackDomains)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    ready.value = search.ready
    degraded.value = search.degraded
    requestCount.value = search.requestCount
    phase.value = search.phase
    errorMessage.value = search.errorMessage
    keyword.value = search.keyword
    activeDomain.value = search.activeDomain
    groups.value = [...search.groups]
    total.value = search.total
    page.value = search.page
    pageSize.value = search.pageSize
    suggestions.value = [...search.suggestions]
    recentKeywords.value = [...search.recentKeywords]
    logItems.value = [...search.logItems]
    logTotal.value = search.logTotal
    logPage.value = search.logPage
    logPageSize.value = search.logPageSize
    logType.value = search.logType
    logRange.value = { ...search.logRange }
    fileItems.value = [...search.fileItems]
    fileTotal.value = search.fileTotal
    filePage.value = search.filePage
    filePageSize.value = search.filePageSize
    fileType.value = search.fileType
    engineDegraded.value = search.engineDegraded
    degradeReason.value = search.degradeReason
  }

  const off = search.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    search.dispose()
  })

  /** 包裹动作：执行后同步响应式面。 */
  const run = <T>(action: () => T): T => {
    const value = action()
    sync()
    return value
  }

  return {
    state: search,
    ready,
    degraded,
    requestCount,
    phase,
    errorMessage,
    keyword,
    activeDomain,
    accessibleDomains,
    groups,
    total,
    page,
    pageSize,
    suggestions,
    recentKeywords,
    logItems,
    logTotal,
    logPage,
    logPageSize,
    logType,
    logRange,
    fileItems,
    fileTotal,
    filePage,
    filePageSize,
    fileType,
    engineDegraded,
    degradeReason,
    hasLogPermission,
    hasFilePermission,
    fallbackDomains,
    setReady: (value) => run(() => search.setReady(value)),
    setEngine: (engine) => run(() => search.setEngine(engine === undefined ? undefined : markRaw(toRaw(engine)))),
    setAccess: (access) => run(() => search.setAccess(access === undefined ? undefined : markRaw(toRaw(access)))),
    setDomains: (domains) => run(() => search.setDomains(domains)),
    setKeyword: (value) => run(() => search.setKeyword(value)),
    setActiveDomain: (key) => run(() => search.setActiveDomain(key)),
    setPage: (value) => run(() => search.setPage(value)),
    setPageSize: (size) => run(() => search.setPageSize(size)),
    setLogRange: (range) => run(() => search.setLogRange(range)),
    setLogType: (value) => run(() => search.setLogType(value)),
    setLogPage: (value) => run(() => search.setLogPage(value)),
    setLogPageSize: (size) => run(() => search.setLogPageSize(size)),
    setFileType: (value) => run(() => search.setFileType(value)),
    setFilePage: (value) => run(() => search.setFilePage(value)),
    setFilePageSize: (size) => run(() => search.setFilePageSize(size)),
    search: async () => {
      const value = await search.search()
      sync()
      return value
    },
    suggest: async () => {
      const value = await search.suggest()
      sync()
      return value
    },
    clearSuggestions: () => run(() => search.clearSuggestions()),
    searchLogs: async () => {
      const value = await search.searchLogs()
      sync()
      return value
    },
    searchFiles: async () => {
      const value = await search.searchFiles()
      sync()
      return value
    },
    addRecentKeyword: (value) => run(() => search.addRecentKeyword(value)),
    removeRecentKeyword: (value) => run(() => search.removeRecentKeyword(value)),
    clearRecentKeywords: () => run(() => search.clearRecentKeywords()),
    registerShortcut: (handler, shortcut = 'mod+k') =>
      onGlobalKeydown((event) => {
        if (matchesShortcut(event, shortcut)) {
          event.preventDefault()
          handler()
        }
      }),
  }
}
