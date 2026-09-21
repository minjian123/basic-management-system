/**
 * 搜索编排能力基类：关键词与域状态、即时建议、多域分组、降级与错误码、
 * 最近搜索、审计日志检索与文件内容检索编排。
 *
 * 父基类 `BasePlaceholderState`（占位语义经链上继承取得）；组件基类 `BaseSearch` 派生其下。
 * 检索通路经注入式 `SearchEngineAdapter`（可替换实现经 `SearchEngineRegistry` 登记），
 * **未注入即占位零请求**；核心不依赖 Vue / DOM / 浏览器 API。
 */

import { BasePlaceholderState } from './placeholder-state'
import { BaseAccess } from './access'
import type { BasePersistedState } from './persisted-state'
import type { SearchEngineAdapter, SearchGlobalRequest, SearchLogRequest, SearchFileRequest } from './search-engine'
import {
  SEARCH_FILE_PERM,
  SEARCH_LOG_PERM,
  SEARCH_PAGE_SIZE_DEFAULT,
  SEARCH_RECENT_MAX,
  addRecentKeyword,
  clampSearchPage,
  clampSearchPageSize,
  filterAccessibleDomains,
  isBlankKeyword,
  normalizeKeyword,
  normalizeRecentKeywords,
  normalizeSearchDomains,
  normalizeSearchHits,
  normalizeSearchResult,
  parseDegradeReason,
  parseDegraded,
  removeRecentKeyword,
  resolveSearchErrorText,
  topHits,
  validateLogRange,
  type SearchDegradeReason,
  type SearchDomain,
  type SearchGroup,
  type SearchHit,
  type SearchPhase,
  type SearchRange,
  type SearchResult,
} from '../domain/search'

/** 搜索编排能力基类（抽象）。 */
export abstract class BaseGlobalSearch extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'global-search'
  /** 依赖登记。 */
  override readonly depends: readonly string[] = ['placeholder-state', 'access', 'persisted-state']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 检索阶段。 */
  phase: SearchPhase = 'idle'
  /** 错误文案。 */
  errorMessage = ''
  /** 错误码。 */
  errorCode: number | undefined
  /** 关键词。 */
  keyword = ''
  /** 当前域（`all` 表示全部可检索域）。 */
  activeDomain = 'all'
  /** 可检索域（宿主传入，含权限码）。 */
  domains: SearchDomain[] = []
  /** 全局检索分组结果。 */
  readonly groups: SearchGroup[] = []
  /** 全局检索命中总数。 */
  total = 0
  /** 全局检索页码（自 1）。 */
  page = 1
  /** 全局检索页长。 */
  pageSize: number = SEARCH_PAGE_SIZE_DEFAULT
  /** 即时建议命中。 */
  readonly suggestions: SearchHit[] = []
  /** 即时建议是否加载中。 */
  suggestLoading = false
  /** 最近搜索（用户维度）。 */
  readonly recentKeywords: string[] = []
  /** 审计日志命中。 */
  readonly logItems: SearchHit[] = []
  /** 审计日志命中总数。 */
  logTotal = 0
  /** 审计日志页码（自 1）。 */
  logPage = 1
  /** 审计日志页长。 */
  logPageSize: number = SEARCH_PAGE_SIZE_DEFAULT
  /** 日志类型（缺省不限定）。 */
  logType = ''
  /** 审计日志时间范围。 */
  logRange: SearchRange = {}
  /** 文件内容命中。 */
  readonly fileItems: SearchHit[] = []
  /** 文件内容命中总数。 */
  fileTotal = 0
  /** 文件内容页码（自 1）。 */
  filePage = 1
  /** 文件内容页长。 */
  filePageSize: number = SEARCH_PAGE_SIZE_DEFAULT
  /** 文件类型（缺省不限定）。 */
  fileType = ''
  /** 检索侧降级标记（10103）。 */
  engineDegraded = false
  /** 降级原因。 */
  degradeReason: SearchDegradeReason | undefined
  /** 检索引擎（注入式；未注入即占位零请求）。 */
  engine: SearchEngineAdapter | undefined
  /** 权限上下文（域二次过滤与页签门控）。 */
  access: BaseAccess | undefined
  /** 偏好持久化通道（最近搜索真源）。 */
  persisted: BasePersistedState | undefined

  /** 竞态序号（防旧响应覆盖）。 */
  #seq = 0

  /** 是否空态。 */
  get empty(): boolean {
    return this.phase === 'empty'
  }

  /** 是否错误态。 */
  get error(): boolean {
    return this.phase === 'error'
  }

  /** 是否进行中。 */
  get busy(): boolean {
    return this.phase === 'loading'
  }

  /** 是否具备审计日志权限（需显式 `log:query`）。 */
  get hasLogPermission(): boolean {
    return this.access?.has(SEARCH_LOG_PERM) ?? false
  }

  /** 是否具备文件内容检索权限（需显式 `file:query`）。 */
  get hasFilePermission(): boolean {
    return this.access?.has(SEARCH_FILE_PERM) ?? false
  }

  /** 可检索域（按权限二次过滤）。 */
  get accessibleDomains(): SearchDomain[] {
    if (this.access === undefined) {
      return this.domains.map((domain) => ({ ...domain }))
    }
    return filterAccessibleDomains(this.domains, new Set(this.access.codes))
  }

  /** 降级替代入口域清单（供宿主装配「前往各域列表」）。 */
  get fallbackDomains(): SearchDomain[] {
    return this.accessibleDomains
  }

  /** 是否可发起全局检索。 */
  get canSearch(): boolean {
    return this.ready && !isBlankKeyword(this.keyword) && typeof this.engine?.searchGlobal === 'function'
  }

  /** 是否可发起审计日志检索。 */
  get canSearchLogs(): boolean {
    return (
      this.ready &&
      this.hasLogPermission &&
      validateLogRange(this.logRange).valid &&
      typeof this.engine?.searchLogs === 'function'
    )
  }

  /** 是否可发起文件内容检索。 */
  get canSearchFiles(): boolean {
    return (
      this.ready &&
      this.hasFilePermission &&
      !isBlankKeyword(this.keyword) &&
      typeof this.engine?.searchFiles === 'function'
    )
  }

  /**
   * 注入 / 移除检索引擎（移除即回落占位零请求）。
   *
   * @param engine 引擎适配器；`undefined` 表示移除。
   */
  setEngine(engine: SearchEngineAdapter | undefined): void {
    this.engine = engine
    this.emitUpdate()
  }

  /**
   * 注入 / 移除权限上下文。
   *
   * @param access 权限上下文；`undefined` 表示移除。
   */
  setAccess(access: BaseAccess | undefined): void {
    this.access = access
    this.emitUpdate()
  }

  /**
   * 挂接偏好持久化通道并恢复最近搜索。
   *
   * @param persisted 偏好持久化能力。
   */
  attachPersisted(persisted: BasePersistedState): void {
    this.persisted = persisted
    this.restoreRecent()
  }

  /**
   * 覆盖可检索域（宿主传入，含权限码）。
   *
   * @param domains 域清单。
   */
  setDomains(domains: readonly SearchDomain[]): void {
    this.domains = normalizeSearchDomains(domains)
    this.emitUpdate()
  }

  /**
   * 设置关键词（归一后写入）。
   *
   * @param keyword 关键词。
   */
  setKeyword(keyword: string): void {
    this.keyword = normalizeKeyword(keyword)
    this.emitUpdate()
  }

  /**
   * 设置当前域。
   *
   * @param key 域标识 / `all`。
   */
  setActiveDomain(key: string): void {
    this.activeDomain = key === '' ? 'all' : key
    this.emitUpdate()
  }

  /**
   * 设置全局检索页码（夹取）。
   *
   * @param page 页码。
   */
  setPage(page: number): void {
    this.page = clampSearchPage(page)
    this.emitUpdate()
  }

  /**
   * 设置全局检索页长（夹取）。
   *
   * @param size 页长。
   */
  setPageSize(size: number): void {
    this.pageSize = clampSearchPageSize(size)
    this.emitUpdate()
  }

  /**
   * 设置日志类型。
   *
   * @param type 日志类型（空串不限定）。
   */
  setLogType(type: string): void {
    this.logType = type
    this.emitUpdate()
  }

  /**
   * 设置审计日志时间范围。
   *
   * @param range 时间范围。
   */
  setLogRange(range: SearchRange): void {
    this.logRange = { ...range }
    this.emitUpdate()
  }

  /**
   * 设置审计日志页码（夹取）。
   *
   * @param page 页码。
   */
  setLogPage(page: number): void {
    this.logPage = clampSearchPage(page)
    this.emitUpdate()
  }

  /**
   * 设置审计日志页长（夹取）。
   *
   * @param size 页长。
   */
  setLogPageSize(size: number): void {
    this.logPageSize = clampSearchPageSize(size)
    this.emitUpdate()
  }

  /**
   * 设置文件类型。
   *
   * @param type 文件类型（空串不限定）。
   */
  setFileType(type: string): void {
    this.fileType = type
    this.emitUpdate()
  }

  /**
   * 设置文件内容页码（夹取）。
   *
   * @param page 页码。
   */
  setFilePage(page: number): void {
    this.filePage = clampSearchPage(page)
    this.emitUpdate()
  }

  /**
   * 设置文件内容页长（夹取）。
   *
   * @param size 页长。
   */
  setFilePageSize(size: number): void {
    this.filePageSize = clampSearchPageSize(size)
    this.emitUpdate()
  }

  /** 当前全局检索参数（与后端契约同源）。 */
  globalParams(): Record<string, unknown> {
    const types = this.activeDomain === 'all' ? this.accessibleDomains.map((domain) => domain.key) : [this.activeDomain]
    return {
      q: this.keyword,
      types,
      page: this.page,
      size: this.pageSize,
    }
  }

  /** 当前审计日志检索参数（与后端契约同源）。 */
  logParams(): Record<string, unknown> {
    return {
      q: this.keyword,
      log_type: this.logType,
      start_time: this.logRange.start,
      end_time: this.logRange.end,
      page: this.logPage,
      size: this.logPageSize,
    }
  }

  /** 当前文件内容检索参数（与后端契约同源）。 */
  fileParams(): Record<string, unknown> {
    return {
      q: this.keyword,
      file_type: this.fileType,
      page: this.filePage,
      size: this.filePageSize,
    }
  }

  /**
   * 全局检索（未就绪 / 未注入引擎不请求）。
   *
   * @returns 分组结果或 `undefined`。
   */
  async search(): Promise<SearchGroup[] | undefined> {
    const engine = this.engine
    if (!this.ready || engine?.searchGlobal === undefined || isBlankKeyword(this.keyword)) {
      return undefined
    }
    const token = (this.#seq += 1)
    this.requestCount += 1
    this.phase = 'loading'
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    const request: SearchGlobalRequest = {
      keyword: this.keyword,
      types:
        this.activeDomain === 'all'
          ? this.accessibleDomains.map((domain) => domain.key)
          : [this.activeDomain],
      page: this.page,
      pageSize: this.pageSize,
    }
    try {
      const raw = await engine.searchGlobal(request)
      if (token !== this.#seq) {
        return undefined
      }
      const result: SearchResult = normalizeSearchResult(raw)
      this.groups.splice(0, this.groups.length, ...result.groups)
      this.total = result.total
      const degraded = readFlag(raw, 'degraded') || result.degraded === true
      this.applyDegrade(degraded, result.degradeReason ?? readReason(raw))
      this.phase = this.groups.length > 0 ? 'ready' : 'empty'
      this.emitUpdate()
      return this.groups.map((group) => ({ ...group, items: group.items.map((item) => ({ ...item })) }))
    } catch (error) {
      if (token !== this.#seq) {
        return undefined
      }
      this.phase = 'error'
      this.errorCode = readErrorCode(error)
      this.errorMessage = resolveSearchErrorText(this.errorCode)
      this.reportError(error, { scope: 'BaseGlobalSearch.search' })
      this.emitUpdate()
      return undefined
    }
  }

  /**
   * 即时建议（防抖由调用方按 `SEARCH_SUGGEST_DEBOUNCE` 触发；未就绪 / 未注入不请求）。
   *
   * @returns 建议命中或 `undefined`。
   */
  async suggest(): Promise<SearchHit[] | undefined> {
    const engine = this.engine
    if (!this.ready || engine?.suggest === undefined || isBlankKeyword(this.keyword)) {
      return undefined
    }
    const token = (this.#seq += 1)
    this.requestCount += 1
    this.suggestLoading = true
    this.emitUpdate()
    try {
      const raw = await engine.suggest({
        keyword: this.keyword,
        types: this.accessibleDomains.map((domain) => domain.key),
      })
      if (token !== this.#seq) {
        return undefined
      }
      const hits = topHits(normalizeSearchHits(raw))
      this.suggestions.splice(0, this.suggestions.length, ...hits)
      this.suggestLoading = false
      this.emitUpdate()
      return hits.map((hit) => ({ ...hit }))
    } catch (error) {
      if (token === this.#seq) {
        this.suggestLoading = false
        this.reportError(error, { scope: 'BaseGlobalSearch.suggest' })
        this.emitUpdate()
      }
      return undefined
    }
  }

  /** 清空即时建议。 */
  clearSuggestions(): void {
    this.suggestions.splice(0, this.suggestions.length)
    this.emitUpdate()
  }

  /**
   * 审计日志检索（`log:query` + 范围合法；未就绪 / 未注入不请求）。
   *
   * @returns 命中或 `undefined`。
   */
  async searchLogs(): Promise<SearchHit[] | undefined> {
    const engine = this.engine
    const validation = validateLogRange(this.logRange)
    if (
      !this.ready ||
      !this.hasLogPermission ||
      engine?.searchLogs === undefined ||
      !validation.valid
    ) {
      if (!validation.valid && this.ready) {
        this.errorMessage = validation.message ?? ''
        this.emitUpdate()
      }
      return undefined
    }
    const token = (this.#seq += 1)
    this.requestCount += 1
    this.phase = 'loading'
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    const request: SearchLogRequest = {
      keyword: this.keyword,
      logType: this.logType,
      start: this.logRange.start ?? '',
      end: this.logRange.end ?? '',
      page: this.logPage,
      pageSize: this.logPageSize,
    }
    try {
      const raw = await engine.searchLogs(request)
      if (token !== this.#seq) {
        return undefined
      }
      const hits = normalizeSearchHits((raw as { items?: unknown } | undefined)?.items ?? raw)
      this.logItems.splice(0, this.logItems.length, ...hits)
      this.logTotal = readTotal(raw, hits.length)
      this.applyDegrade(readFlag(raw, 'degraded'), readReason(raw))
      this.phase = this.logItems.length > 0 ? 'ready' : 'empty'
      this.emitUpdate()
      return hits.map((hit) => ({ ...hit }))
    } catch (error) {
      if (token !== this.#seq) {
        return undefined
      }
      this.phase = 'error'
      this.errorCode = readErrorCode(error)
      this.errorMessage = resolveSearchErrorText(this.errorCode)
      this.reportError(error, { scope: 'BaseGlobalSearch.searchLogs' })
      this.emitUpdate()
      return undefined
    }
  }

  /**
   * 文件内容检索（`file:query`；未就绪 / 未注入不请求）。
   *
   * @returns 命中或 `undefined`。
   */
  async searchFiles(): Promise<SearchHit[] | undefined> {
    const engine = this.engine
    if (!this.ready || !this.hasFilePermission || engine?.searchFiles === undefined || isBlankKeyword(this.keyword)) {
      return undefined
    }
    const token = (this.#seq += 1)
    this.requestCount += 1
    this.phase = 'loading'
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    const request: SearchFileRequest = {
      keyword: this.keyword,
      fileType: this.fileType,
      page: this.filePage,
      pageSize: this.filePageSize,
    }
    try {
      const raw = await engine.searchFiles(request)
      if (token !== this.#seq) {
        return undefined
      }
      const hits = normalizeSearchHits((raw as { items?: unknown } | undefined)?.items ?? raw)
      this.fileItems.splice(0, this.fileItems.length, ...hits)
      this.fileTotal = readTotal(raw, hits.length)
      this.applyDegrade(readFlag(raw, 'degraded'), readReason(raw))
      this.phase = this.fileItems.length > 0 ? 'ready' : 'empty'
      this.emitUpdate()
      return hits.map((hit) => ({ ...hit }))
    } catch (error) {
      if (token !== this.#seq) {
        return undefined
      }
      this.phase = 'error'
      this.errorCode = readErrorCode(error)
      this.errorMessage = resolveSearchErrorText(this.errorCode)
      this.reportError(error, { scope: 'BaseGlobalSearch.searchFiles' })
      this.emitUpdate()
      return undefined
    }
  }

  /**
   * 追加最近搜索（去重置顶 + 上限 + 落盘）。
   *
   * @param keyword 关键词。
   */
  addRecentKeyword(keyword: string): void {
    const next = addRecentKeyword(this.recentKeywords, keyword, SEARCH_RECENT_MAX)
    this.recentKeywords.splice(0, this.recentKeywords.length, ...next)
    this.persistRecent()
    this.emitUpdate()
  }

  /**
   * 移除最近搜索并落盘。
   *
   * @param keyword 关键词。
   */
  removeRecentKeyword(keyword: string): void {
    const next = removeRecentKeyword(this.recentKeywords, keyword)
    this.recentKeywords.splice(0, this.recentKeywords.length, ...next)
    this.persistRecent()
    this.emitUpdate()
  }

  /** 清空最近搜索并落盘。 */
  clearRecentKeywords(): void {
    this.recentKeywords.splice(0, this.recentKeywords.length)
    this.persistRecent()
    this.emitUpdate()
  }

  /**
   * 把最近搜索写入本地存储（无持久化通道返回 `false`）。
   *
   * @returns 是否写入成功。
   */
  persistRecent(): boolean {
    if (this.persisted === undefined) {
      return false
    }
    this.persisted.setLocal([...this.recentKeywords])
    return this.persisted.persist()
  }

  /**
   * 从本地存储恢复最近搜索（无持久化通道返回 `false`）。
   *
   * @returns 是否恢复成功。
   */
  restoreRecent(): boolean {
    if (this.persisted === undefined || !this.persisted.restore()) {
      return false
    }
    const restored = normalizeRecentKeywords(this.persisted.local, SEARCH_RECENT_MAX)
    this.recentKeywords.splice(0, this.recentKeywords.length, ...restored)
    this.emitUpdate()
    return true
  }

  /**
   * 应用降级标记（仅置位，不清零；`search` 前重置）。
   *
   * @param degraded 是否降级。
   * @param reason 降级原因。
   */
  private applyDegrade(degraded: boolean, reason: SearchDegradeReason | undefined): void {
    this.engineDegraded = degraded
    this.degradeReason = degraded ? reason : undefined
  }

  /** 广播更新（已释放则忽略）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}

/**
 * 读取结果总数（非有限值回落命中条数）。
 *
 * @param raw 原始结果。
 * @param fallback 回落条数。
 * @returns 总数。
 */
function readTotal(raw: unknown, fallback: number): number {
  if (raw !== null && typeof raw === 'object' && !Array.isArray(raw)) {
    const total = (raw as { total?: unknown }).total
    if (typeof total === 'number' && Number.isFinite(total) && total >= 0) {
      return Math.floor(total)
    }
  }
  return fallback
}

/**
 * 读取降级标记。
 *
 * @param raw 原始结果。
 * @param key 字段名。
 * @returns 是否降级。
 */
function readFlag(raw: unknown, key: string): boolean {
  if (raw !== null && typeof raw === 'object' && !Array.isArray(raw)) {
    return parseDegraded((raw as Record<string, unknown>)[key])
  }
  return false
}

/**
 * 读取降级原因（兼容 `degradeReason` / `degrade_reason`）。
 *
 * @param raw 原始结果。
 * @returns 降级原因或 `undefined`。
 */
function readReason(raw: unknown): SearchDegradeReason | undefined {
  if (raw !== null && typeof raw === 'object' && !Array.isArray(raw)) {
    const source = raw as Record<string, unknown>
    return parseDegradeReason(source.degradeReason ?? source.degrade_reason)
  }
  return undefined
}

/**
 * 读取错误码（兼容 `code` / `errorCode`）。
 *
 * @param error 原始错误。
 * @returns 错误码或 `undefined`。
 */
function readErrorCode(error: unknown): number | undefined {
  if (error !== null && typeof error === 'object') {
    const raw = error as { code?: unknown; errorCode?: unknown }
    const code = typeof raw.code === 'number' ? raw.code : raw.errorCode
    if (typeof code === 'number' && Number.isFinite(code)) {
      return code
    }
  }
  return undefined
}
