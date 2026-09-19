/**
 * 文案目录编排能力基类：语言清单维护 / 文案网格取数与编辑 / 增删 `msg_key` / 筛选 /
 * 内容派生幂等键批量保存 / 缓存主动失效与语言包重载 / 脏数据基线与撤销。
 *
 * **数据通路由宿主注入**（语言清单取数与增改启停、文案维护取数、批量保存、缓存失效、语言包重载）——
 * 未注入即占位：不发请求、返回 `undefined` / `false`、写占位文案；聚焦语言经组合的 `BaseLocale` 承载。
 * 核心不触 DOM、不发请求；Excel 列头核对与行级校验归后端。
 */

import { BaseComponent } from '../base/BaseComponent'
import {
  DEFAULT_LOCALE,
  EMPTY_I18N_FILTER,
  I18N_CACHE_FAILED_TEXT,
  I18N_CACHE_PLACEHOLDER_TEXT,
  I18N_DUPLICATE_KEY_TEXT,
  I18N_NO_CHANGE_TEXT,
  I18N_PLACEHOLDER_TEXT,
  I18N_PERM,
  I18N_RELOAD_FAILED_TEXT,
  I18N_RELOAD_PLACEHOLDER_TEXT,
  I18N_SAVE_PLACEHOLDER_TEXT,
  MESSAGE_PAGE_SIZE,
  MESSAGE_VIRTUAL_THRESHOLD,
  deriveMessageKey,
  deriveMissingLocales,
  diffMessages,
  filterMessages,
  isDirty,
  localeColumns,
  normalizeLocale,
  normalizeLocales,
  normalizeMessage,
  normalizeMessages,
  normalizeMessageKey,
  paginateMessages,
  resolveFilterParams,
  shouldVirtualize,
  validateLocaleAdd,
  validateLocaleRemove,
  validateLocaleToggle,
  validateLocaleUpdate,
  validateMessageKey,
  validateMessageValue,
  type I18nChangeSet,
  type I18nCheckResult,
  type I18nFilter,
  type I18nLocaleInput,
  type I18nLocaleItem,
  type I18nMessageInput,
  type I18nMessageItem,
} from '../domain/i18n'
import type { BaseAccess } from './access'
import type { BaseLocale } from './locale'
import type { BaseNotice } from './notice'

/** 编排阶段。 */
export type MessagePhase = 'idle' | 'loading' | 'saving' | 'invalidating' | 'done' | 'failed'

/** 语言清单变更种类。 */
export type LocaleChangeKind = 'add' | 'update' | 'toggle' | 'remove'

/** 语言清单变更请求。 */
export interface LocaleChangeInput {
  /** 变更种类。 */
  kind: LocaleChangeKind
  /** 语言项（`update` / `toggle` / `remove` 时 `code` 必填）。 */
  locale: I18nLocaleInput
  /** 启停目标状态（`toggle` 用）。 */
  enabled?: boolean
}

/** 文案维护取数入参。 */
export interface MessageLoadInput {
  /** 页码（从 1 起）。 */
  page: number
  /** 每页行数。 */
  size: number
  /** 下发后端的筛选参数。 */
  params: Record<string, unknown>
  /** 语言列集（启用语言标识）。 */
  localeCodes: readonly string[]
}

/** 批量保存入参。 */
export interface MessageSaveInput {
  /** 内容派生幂等键（`Idempotency-Key`）。 */
  idempotencyKey: string
  /** 新增或更新的行。 */
  upserts: readonly { key: string; values: Record<string, string> }[]
  /** 删除的 key。 */
  removedKeys: readonly string[]
  /** 语言清单。 */
  locales: readonly I18nLocaleItem[]
}

/** 注入的处理函数集（未注入的项按占位：不请求、不动作）。 */
export interface MessageJobs {
  /** 语言清单取数。 */
  loadLocales?: () => Promise<readonly I18nLocaleInput[] | undefined>
  /** 语言清单变更提交。 */
  saveLocale?: (input: LocaleChangeInput) => Promise<void>
  /** 文案维护列表取数。 */
  loadMessages?: (input: MessageLoadInput) => Promise<{ rows: readonly I18nMessageInput[]; total: number } | undefined>
  /** 批量保存。 */
  save?: (input: MessageSaveInput) => Promise<void>
  /** 缓存主动失效（`PUT /i18n/cache/invalidate`）。 */
  invalidateCache?: () => Promise<void>
  /** 语言包重载（重新拉取并注入运行时语言包）。 */
  reloadMessages?: () => Promise<void>
}

/** 保存结果。 */
export interface SaveResult {
  /** 内容派生幂等键。 */
  idempotencyKey: string
  /** 保存行数（更新 + 删除）。 */
  changed: number
  /** 缓存是否已失效。 */
  cacheInvalidated: boolean
  /** 语言包是否已重载。 */
  reloaded: boolean
}

/** 空筛选条件（只读快照）。 */
const FILTER_DEFAULTS: I18nFilter = { ...EMPTY_I18N_FILTER }

/** 文案目录编排能力基类（抽象）。 */
export abstract class BaseMessageCatalog extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'message-catalog'
  /** 依赖能力键（语言上下文 / 权限 / 提示）。 */
  override readonly depends = ['locale', 'access', 'notice']
  /** 业务标识（后端路径段，导入导出复用）。 */
  biz = 'i18n'
  /** 业务中文名（导出文件名与标题）。 */
  bizName = '语言包'
  /** 数据通路是否就绪（占位语义开关）。 */
  ready = false
  /** 实际发起的请求计数（占位期恒 0）。 */
  requestCount = 0
  /** 当前阶段。 */
  phase: MessagePhase = 'idle'
  /** 语言清单（运行态）。 */
  locales: I18nLocaleItem[] = []
  /** 默认语言（不可停用）。 */
  defaultLocale: string = DEFAULT_LOCALE
  /** 当前页文案行。 */
  messages: I18nMessageItem[] = []
  /** 总条数。 */
  total = 0
  /** 当前页码。 */
  page = 1
  /** 每页行数。 */
  pageSize: number = MESSAGE_PAGE_SIZE
  /** 筛选条件。 */
  filter: I18nFilter = { ...FILTER_DEFAULTS }
  /** 聚焦语言（与语言上下文同源）。 */
  activeLocale = ''
  /** 是否显示停用语言列（置灰仍占位）。 */
  showDisabledLocales = false
  /** 虚拟滚动阈值。 */
  virtualThreshold: number = MESSAGE_VIRTUAL_THRESHOLD
  /** 语言包版本号（每次重载成功递增）。 */
  messagesRevision = 0
  /** 提示 / 失败文案。 */
  errorMessage = ''
  /** 最近错误码（0 表示无）。 */
  errorCode = 0
  /** 取数基线（脏数据判定与「仅已修改」用）。 */
  baseline: I18nMessageItem[] = []
  /** 宿主注入的处理函数集。 */
  jobs: MessageJobs = {}
  /** 语言上下文（组合；聚焦语言经其承载）。 */
  localeContext: BaseLocale | undefined
  /** 权限上下文（未注入不校验）。 */
  access: BaseAccess | undefined
  /** 提示通知（未注入不发通知）。 */
  notice: BaseNotice | undefined

  /** 是否降级（占位）态。 */
  get degraded(): boolean {
    return !this.ready
  }

  /** 是否进行中（取数 / 保存 / 失效）。 */
  get busy(): boolean {
    return this.phase === 'loading' || this.phase === 'saving' || this.phase === 'invalidating'
  }

  /** 是否存在未保存变更。 */
  get dirty(): boolean {
    return isDirty(this.baseline, this.messages)
  }

  /** 当前变更集。 */
  get changeSet(): I18nChangeSet {
    return diffMessages(this.baseline, this.messages, this.locales)
  }

  /** 内容派生幂等键（同一变更集同键、改一处换键）。 */
  get idempotencyKey(): string {
    return deriveMessageKey(this.changeSet)
  }

  /** 是否可保存（就绪 ∧ 非进行中 ∧ 有权 ∧ 有变更）。 */
  get canSave(): boolean {
    return this.ready && !this.busy && this.dirty && this.isAllowed(I18N_PERM)
  }

  /** 存在缺失翻译的启用语言。 */
  get missingCodes(): string[] {
    const enabled = localeColumns(this.locales)
    return enabled
      .filter((item) => this.messages.some((row) => row.values[item.code] === undefined || row.values[item.code] === ''))
      .map((item) => item.code)
  }

  /** 列集（是否含停用语言由 `showDisabledLocales` 决定）。 */
  get columns(): I18nLocaleItem[] {
    return localeColumns(this.locales, this.showDisabledLocales)
  }

  /** 当前页按筛选条件本地过滤后的行（缺失 / 仅已修改为本地判定）。 */
  get visibleMessages(): I18nMessageItem[] {
    return filterMessages(this.messages, this.filter, this.baseline)
  }

  /** 已修改行的键（「仅已修改」标记用）。 */
  get modifiedKeys(): string[] {
    const baselineMap = new Map(this.baseline.map((row) => [row.key, row]))
    return this.messages
      .filter((row) => {
        const base = baselineMap.get(row.key)
        return base === undefined || JSON.stringify(base.values) !== JSON.stringify(row.values)
      })
      .map((row) => row.key)
  }

  /** 是否切换虚拟滚动。 */
  get virtualized(): boolean {
    return shouldVirtualize(this.visibleMessages.length, this.virtualThreshold)
  }

  /** 总页数（至少 1）。 */
  get pageCount(): number {
    return paginateMessages(this.messages, this.page, this.pageSize).pageCount
  }

  /** 下发后端的筛选参数。 */
  get exportParams(): Record<string, unknown> {
    return resolveFilterParams(this.filter)
  }

  /**
   * 设置就绪态（占位语义开关）。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    if (this.ready === value) {
      return
    }
    this.ready = value
    this.touch()
  }

  /**
   * 注入处理函数集（整体替换）。
   *
   * @param jobs 处理函数集。
   */
  setJobs(jobs: MessageJobs): void {
    this.jobs = jobs
    this.touch()
  }

  /**
   * 应用外部下发快照（件层 props 下发面；同时置基线，视为「已保存态」）。
   *
   * 语义：宿主下发数据即已持久化内容，故与基线同值（`dirty` 归假）；编辑后由 `diffMessages` 判定脏态。
   *
   * @param input 快照输入。
   */
  applySnapshot(input: {
    locales?: readonly I18nLocaleInput[]
    messages?: readonly I18nMessageInput[]
    total?: number
  }): void {
    if (input.locales !== undefined) {
      this.locales = normalizeLocales(input.locales)
    }
    if (input.messages !== undefined) {
      this.messages = normalizeMessages(input.messages, this.locales)
      this.baseline = cloneRows(this.messages)
    }
    if (input.total !== undefined) {
      this.total = input.total
    } else if (this.total === 0) {
      this.total = this.messages.length
    }
    this.page = paginateMessages(this.messages, this.page, this.pageSize).page
    this.touch()
  }

  /**
   * 更新筛选条件（合并；变更由件层放行后触发重取）。
   *
   * @param filter 部分筛选条件。
   */
  setFilter(filter: Partial<I18nFilter>): void {
    this.filter = { ...this.filter, ...filter }
    this.touch()
  }

  /**
   * 设置聚焦语言（同时写入语言上下文）。
   *
   * @param code 语言标识（空串表示不聚焦）。
   */
  setActiveLocale(code: string): void {
    const next = String(code ?? '').trim()
    this.activeLocale = next
    if (next !== '') {
      this.localeContext?.setLocale(next)
    }
    this.touch()
  }

  /**
   * 切换是否显示停用语言列。
   *
   * @param value 是否显示。
   */
  setShowDisabledLocales(value: boolean): void {
    this.showDisabledLocales = value
    this.touch()
  }

  /**
   * 设置虚拟滚动阈值。
   *
   * @param value 阈值。
   */
  setVirtualThreshold(value: number): void {
    this.virtualThreshold = value
    this.touch()
  }

  /**
   * 切换页码（夹取到有效范围）。
   *
   * @param page 目标页码。
   */
  setPage(page: number): void {
    this.page = paginateMessages(this.messages, page, this.pageSize).page
    this.touch()
  }

  /**
   * 设置每页行数（页码回落首页）。
   *
   * @param size 每页行数。
   */
  setPageSize(size: number): void {
    this.pageSize = Math.max(1, Math.floor(size) || 1)
    this.page = 1
    this.touch()
  }

  /**
   * 取数（语言清单 + 当前页文案）；成功置基线。
   *
   * @returns 是否成功；占位 / 未注入取数时返回 `false`。
   */
  async load(): Promise<boolean> {
    if (!this.ready) {
      return false
    }
    const jobs = this.jobs
    if (jobs.loadLocales === undefined && jobs.loadMessages === undefined) {
      this.errorMessage = I18N_PLACEHOLDER_TEXT
      this.touch()
      return false
    }
    this.phase = 'loading'
    this.errorMessage = ''
    this.errorCode = 0
    this.requestCount += 1
    this.touch()
    try {
      if (jobs.loadLocales !== undefined) {
        const locales = await jobs.loadLocales()
        if (locales !== undefined) {
          this.locales = normalizeLocales(locales)
        }
      }
      if (jobs.loadMessages !== undefined) {
        const payload = await jobs.loadMessages({
          page: this.page,
          size: this.pageSize,
          params: resolveFilterParams(this.filter),
          localeCodes: localeColumns(this.locales).map((item) => item.code),
        })
        if (payload !== undefined) {
          this.total = payload.total
          this.messages = normalizeMessages(payload.rows, this.locales)
        }
      }
      this.page = paginateMessages(this.messages, this.page, this.pageSize).page
      this.baseline = cloneRows(this.messages)
      this.phase = 'done'
      this.touch()
      return true
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = resolveErrorText(error, '文案取数失败')
      this.errorCode = resolveErrorCode(error)
      this.notice?.enqueue(this.errorMessage, 'error')
      this.touch()
      return false
    }
  }

  /** 保留筛选与页码重取当前页（成功置基线）。 */
  async reload(): Promise<boolean> {
    return this.load()
  }

  /**
   * 编辑单元格（值超长 / 未知语言 / 停用语言拒绝）。
   *
   * @param input 单元格输入。
   * @returns 是否写入成功。
   */
  editCell(input: { key: string; locale: string; value: string }): boolean {
    const row = this.messages.find((item) => item.key === input.key)
    const locale = this.locales.find((item) => item.code === input.locale)
    if (row === undefined || locale === undefined || locale.status !== 'enabled') {
      return false
    }
    const check = validateMessageValue(input.value)
    if (!check.valid) {
      this.errorMessage = check.message
      this.errorCode = check.code
      this.touch()
      return false
    }
    row.values = { ...row.values, [input.locale]: String(input.value) }
    row.missing = deriveMissingLocales(row.values, localeColumns(this.locales))
    this.errorMessage = ''
    this.errorCode = 0
    this.touch()
    return true
  }

  /**
   * 新增 `msg_key`（命名非法与重复拒绝）。
   *
   * @param input 新增输入。
   * @returns 是否新增成功。
   */
  addKey(input: { key: string; values?: Record<string, string> }): boolean {
    const key = normalizeMessageKey(input.key)
    const check = validateMessageKey(key)
    if (!check.valid) {
      this.errorMessage = check.message
      this.errorCode = check.code
      this.touch()
      return false
    }
    if (this.messages.some((row) => row.key === key)) {
      this.errorMessage = I18N_DUPLICATE_KEY_TEXT
      this.errorCode = 0
      this.touch()
      return false
    }
    this.messages = [...this.messages, normalizeMessage({ key, values: input.values }, this.locales)]
    this.errorMessage = ''
    this.errorCode = 0
    this.touch()
    return true
  }

  /**
   * 删除 `msg_key`（本地移除，待保存提交）。
   *
   * @param key 文案键。
   * @returns 是否存在并移除。
   */
  removeKey(key: string): boolean {
    const target = normalizeMessageKey(key)
    const next = this.messages.filter((row) => row.key !== target)
    if (next.length === this.messages.length) {
      return false
    }
    this.messages = next
    this.touch()
    return true
  }

  /**
   * 新增语言（本地生效后异步提交；提交失败回滚）。
   *
   * @param input 语言输入。
   * @returns 校验结果。
   */
  addLocale(input: I18nLocaleInput): I18nCheckResult {
    const check = validateLocaleAdd(input, this.locales)
    if (!check.valid) {
      this.rejectCheck(check)
      return check
    }
    const snapshot = cloneLocales(this.locales)
    this.locales = [...this.locales, normalizeLocale(input)]
    this.touch()
    this.commitLocale({ kind: 'add', locale: input }, snapshot)
    return check
  }

  /**
   * 修改语言（名称 / RTL / 启停；`code` 不可改）。
   *
   * @param code 原语言标识。
   * @param patch 修改内容。
   * @returns 校验结果。
   */
  updateLocale(code: string, patch: I18nLocaleInput): I18nCheckResult {
    const check = validateLocaleUpdate(code, patch, this.locales, this.defaultLocale)
    if (!check.valid) {
      this.rejectCheck(check)
      return check
    }
    const snapshot = cloneLocales(this.locales)
    this.locales = this.locales.map((item) =>
      item.code === code
        ? { ...item, name: patch.name ?? item.name, rtl: patch.rtl ?? item.rtl, status: patch.status ?? item.status }
        : item,
    )
    this.touch()
    this.commitLocale({ kind: 'update', locale: { ...patch, code } }, snapshot)
    return check
  }

  /**
   * 启停语言（默认语言与「至少一种启用」由 `domain/i18n` 校验拒绝）。
   *
   * @param code 语言标识。
   * @param enabled 目标状态。
   * @returns 校验结果。
   */
  toggleLocale(code: string, enabled: boolean): I18nCheckResult {
    const check = validateLocaleToggle(code, enabled, this.locales, this.defaultLocale)
    if (!check.valid) {
      this.rejectCheck(check)
      return check
    }
    const snapshot = cloneLocales(this.locales)
    this.locales = this.locales.map((item) =>
      item.code === code ? { ...item, status: enabled ? 'enabled' : 'disabled' } : item,
    )
    this.touch()
    this.commitLocale({ kind: 'toggle', locale: { code }, enabled }, snapshot)
    return check
  }

  /**
   * 删除语言（有语言包数据 / 默认语言 / 仅剩一种拒绝）。
   *
   * @param code 语言标识。
   * @returns 校验结果。
   */
  removeLocale(code: string): I18nCheckResult {
    const hasMessages = this.messages.some((row) => String(row.values[code] ?? '').trim() !== '')
    const check = validateLocaleRemove(code, this.locales, hasMessages, this.defaultLocale)
    if (!check.valid) {
      this.rejectCheck(check)
      return check
    }
    const snapshot = cloneLocales(this.locales)
    this.locales = this.locales.filter((item) => item.code !== code)
    this.touch()
    this.commitLocale({ kind: 'remove', locale: { code } }, snapshot)
    return check
  }

  /**
   * 批量保存（内容派生幂等键；成功后重置基线并依次失效缓存与重载语言包）。
   *
   * @returns 保存结果；占位 / 未注入 / 无变更 / key 校验失败时返回 `undefined`。
   */
  async save(): Promise<SaveResult | undefined> {
    if (!this.ready || this.busy) {
      return undefined
    }
    if (!this.isAllowed(I18N_PERM)) {
      this.errorMessage = '无语言包维护权限'
      this.touch()
      return undefined
    }
    const invalid = this.messages.find((row) => !validateMessageKey(row.key).valid)
    if (invalid !== undefined) {
      const check = validateMessageKey(invalid.key)
      this.rejectCheck(check)
      return undefined
    }
    const changeSet = this.changeSet
    if (changeSet.upserts.length === 0 && changeSet.removedKeys.length === 0) {
      this.errorMessage = I18N_NO_CHANGE_TEXT
      this.errorCode = 0
      this.touch()
      return undefined
    }
    const handler = this.jobs.save
    if (handler === undefined) {
      this.errorMessage = I18N_SAVE_PLACEHOLDER_TEXT
      this.touch()
      return undefined
    }
    const idempotencyKey = deriveMessageKey(changeSet)
    const changed = changeSet.upserts.length + changeSet.removedKeys.length
    this.phase = 'saving'
    this.errorMessage = ''
    this.errorCode = 0
    this.requestCount += 1
    this.touch()
    try {
      await handler({
        idempotencyKey,
        upserts: changeSet.upserts,
        removedKeys: changeSet.removedKeys,
        locales: changeSet.locales,
      })
    } catch (error) {
      this.phase = 'failed'
      this.errorMessage = resolveErrorText(error, '批量保存失败')
      this.errorCode = resolveErrorCode(error)
      this.notice?.enqueue(this.errorMessage, 'error')
      this.touch()
      return undefined
    }
    this.baseline = cloneRows(this.messages)
    const localeSnapshot = cloneLocales(this.locales)
    const cacheInvalidated = await this.invalidateCache()
    const reloaded = await this.reloadMessages()
    this.locales = localeSnapshot
    this.phase = 'done'
    if (cacheInvalidated) {
      this.notice?.enqueue('保存成功', 'success')
    } else {
      this.notice?.enqueue(I18N_CACHE_FAILED_TEXT, 'warning')
    }
    this.touch()
    return { idempotencyKey, changed, cacheInvalidated, reloaded }
  }

  /**
   * 重试上一次失败保存（**复用同一内容派生幂等键**）。
   *
   * @returns 保存结果；非失败态时返回 `undefined`。
   */
  async retry(): Promise<SaveResult | undefined> {
    if (this.phase !== 'failed') {
      return undefined
    }
    return this.save()
  }

  /**
   * 缓存主动失效（失败写提示并返回 `false`，不视为失败态）。
   *
   * @returns 是否失效成功；占位 / 未注入时返回 `false`。
   */
  async invalidateCache(): Promise<boolean> {
    if (!this.ready) {
      return false
    }
    const handler = this.jobs.invalidateCache
    if (handler === undefined) {
      this.errorMessage = I18N_CACHE_PLACEHOLDER_TEXT
      this.touch()
      return false
    }
    const previous = this.phase
    this.phase = 'invalidating'
    this.requestCount += 1
    this.touch()
    try {
      await handler()
      this.phase = previous === 'done' || previous === 'idle' ? previous : 'done'
      this.touch()
      return true
    } catch (error) {
      this.errorMessage = I18N_CACHE_FAILED_TEXT
      this.errorCode = resolveErrorCode(error)
      this.notice?.enqueue(I18N_CACHE_FAILED_TEXT, 'warning')
      this.phase = previous === 'idle' ? 'idle' : 'done'
      this.touch()
      return false
    }
  }

  /**
   * 语言包重载（成功后递增版本号并应用聚焦语言）。
   *
   * @returns 是否重载成功；占位 / 未注入时返回 `false`。
   */
  async reloadMessages(): Promise<boolean> {
    if (!this.ready) {
      return false
    }
    const handler = this.jobs.reloadMessages
    if (handler === undefined) {
      this.errorMessage = I18N_RELOAD_PLACEHOLDER_TEXT
      this.touch()
      return false
    }
    const previous = this.phase
    this.phase = 'loading'
    this.requestCount += 1
    this.touch()
    try {
      await handler()
      this.messagesRevision += 1
      if (this.activeLocale !== '') {
        this.localeContext?.setLocale(this.activeLocale)
      }
      this.phase = previous === 'done' || previous === 'idle' ? previous : 'done'
      this.touch()
      return true
    } catch (error) {
      this.errorMessage = I18N_RELOAD_FAILED_TEXT
      this.errorCode = resolveErrorCode(error)
      this.notice?.enqueue(I18N_RELOAD_FAILED_TEXT, 'warning')
      this.phase = previous === 'idle' ? 'idle' : 'done'
      this.touch()
      return false
    }
  }

  /** 撤销未保存变更（回到基线）。 */
  resetDirty(): void {
    this.messages = cloneRows(this.baseline).map((row) => normalizeMessage(row, this.locales))
    this.errorMessage = ''
    this.errorCode = 0
    this.phase = this.phase === 'failed' ? 'idle' : this.phase
    this.touch()
  }

  /** 整体复位（保留注入、语言清单与上下文）。 */
  reset(): void {
    this.messages = []
    this.baseline = []
    this.total = 0
    this.page = 1
    this.filter = { ...FILTER_DEFAULTS }
    this.errorMessage = ''
    this.errorCode = 0
    this.phase = 'idle'
    this.touch()
  }

  /**
   * 是否具备某权限码（权限上下文未注入或权限码为空时视为有权）。
   *
   * @param perm 权限码。
   * @returns 是否具备。
   */
  isAllowed(perm: string): boolean {
    if (perm === '' || this.access === undefined) {
      return true
    }
    return this.access.has(perm)
  }

  /**
   * 提交语言清单变更（未注入即占位不请求；失败回滚本地清单）。
   *
   * @param change 变更请求。
   * @param snapshot 回滚快照。
   */
  private commitLocale(change: LocaleChangeInput, snapshot: I18nLocaleItem[]): void {
    const handler = this.jobs.saveLocale
    if (!this.ready || handler === undefined) {
      return
    }
    this.requestCount += 1
    void handler(change).catch((error: unknown) => {
      this.locales = snapshot
      this.errorMessage = resolveErrorText(error, '语言清单提交失败')
      this.errorCode = resolveErrorCode(error)
      this.notice?.enqueue(this.errorMessage, 'error')
      this.touch()
    })
  }

  /**
   * 记录校验失败（写文案与错误码）。
   *
   * @param check 校验结果。
   */
  private rejectCheck(check: I18nCheckResult): void {
    this.errorMessage = check.message
    this.errorCode = check.code
    this.touch()
  }

  /** 通知变更（已释放时跳过）。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}

/**
 * 深拷贝文案行集合。
 *
 * @param rows 文案行。
 * @returns 拷贝。
 */
function cloneRows(rows: readonly I18nMessageItem[]): I18nMessageItem[] {
  return rows.map((row) => ({ key: row.key, values: { ...row.values }, missing: [...row.missing] }))
}

/**
 * 深拷贝语言清单。
 *
 * @param locales 语言清单。
 * @returns 拷贝。
 */
function cloneLocales(locales: readonly I18nLocaleItem[]): I18nLocaleItem[] {
  return locales.map((item) => ({ ...item }))
}

/**
 * 提取失败文案。
 *
 * @param error 异常。
 * @param fallback 兜底文案。
 */
function resolveErrorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message !== '' ? error.message : fallback
}

/**
 * 提取错误码（后端错误对象可选携带 `code`）。
 *
 * @param error 异常。
 */
function resolveErrorCode(error: unknown): number {
  if (typeof error === 'object' && error !== null) {
    const code = (error as { code?: unknown }).code
    if (typeof code === 'number' && Number.isFinite(code)) {
      return code
    }
  }
  return 0
}
