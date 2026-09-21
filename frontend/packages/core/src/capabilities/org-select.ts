/**
 * 组织选择族组件基类：用户 / 岗位 / 部门三类远程搜索、批量按 id 回显、缓存、
 * 已删除 / 停用占位、多选上限，以及部门树一次性加载。
 *
 * 全链：`BaseComponent → BasePlaceholderState → BaseValue → BaseField → BaseOptionSource → BaseOrgSelect → 具体件`。
 * 数据通路经注入式 `OrgSourceAdapter`（可替换实现经 `OrgSourceRegistry` 登记），**未注入即占位零请求**；
 * 用户展示经注入的 `BaseUserDisplay` 花名册解析；核心不依赖 Vue / DOM / 浏览器 API。
 */

import { BaseOptionSource } from './option-source'
import type { BaseUserDisplay, UserDisplayInfo } from './user-display'
import type { OrgSourceAdapter, OrgPostQuery, OrgUserQuery } from './org-source'
import {
  ORG_DEFAULT_PAGE_SIZE,
  ORG_EMPTY_VALUE,
  ORG_LOAD_ERROR_TEXT,
  ORG_LIMIT_DEFAULT,
  ORG_CACHE_MAX,
  applyOrgSelection,
  buildOrgResolveQuery,
  clampOrgPage,
  findOrgDeptPath,
  findOrgItem,
  isOrgErrorCode,
  mergeOrgItems,
  normalizeOrgIds,
  normalizeOrgKeyword,
  normalizeOrgNameRefs,
  normalizeOrgSearchQuery,
  orgCacheKey,
  orgItemLabel,
  orgLimitText,
  orgSelectionText,
  orgTagSummary,
  parseOrgDeptTree,
  parseOrgPage,
  removeOrgId,
  resolveOrgErrorText,
  type OrgDeptNode,
  type OrgKind,
  type OrgOptionItem,
  type OrgSearchQuery,
  type OrgStatus,
  type OrgTagSummary,
} from '../domain/org'

/** 组织选择族组件基类（抽象）。 */
export abstract class BaseOrgSelect extends BaseOptionSource<string | string[]> {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'org-select'
  /** 依赖登记。 */
  override readonly depends = ['option-source', 'user-display']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 对象类型。 */
  kind: OrgKind = 'user'
  /** 搜索关键词。 */
  keyword = ''
  /** 部门过滤标识。 */
  deptId = ''
  /** 部门过滤是否含下级。 */
  includeChildren = false
  /** 状态过滤（空串不限定）。 */
  status: OrgStatus | '' = ''
  /** 是否多选。 */
  multiple = false
  /** 多选上限（0 不限）。 */
  limit: number = ORG_LIMIT_DEFAULT
  /** 候选页码（自 1；复合选择分页用）。 */
  page = 1
  /** 候选总数（服务端返回，非有限值回落当前条数）。 */
  total = 0
  /** 候选与已选富对象（常驻内存，按 id 合并）。 */
  readonly items: OrgOptionItem[] = []
  /** 部门树（一次性加载，会话缓存）。 */
  readonly deptNodes: OrgDeptNode[] = []
  /** 多选超限标记。 */
  limitExceeded = false
  /** 错误码。 */
  errorCode: number | undefined
  /** 错误文案。 */
  errorMessage = ''
  /** 组织数据源（注入式；未注入即占位零请求）。 */
  source: OrgSourceAdapter | undefined
  /** 用户展示能力（注入引用；用户姓名 / 头像 / 状态 / 部门路径统一经其解析）。 */
  userDisplay: BaseUserDisplay | undefined

  /** 关键词结果短缓存（键 → 候选）。 */
  readonly #cache = new Map<string, OrgOptionItem[]>()
  /** 候选请求序号（防旧响应覆盖）。 */
  #listSeq = 0
  /** 回显请求序号。 */
  #resolveSeq = 0
  /** 部门树请求序号。 */
  #treeSeq = 0
  /** 部门树是否已加载（空树亦视为已加载）。 */
  #deptLoaded = false

  /** 是否错误态。 */
  get error(): boolean {
    return this.errorCode !== undefined
  }

  /** 是否空态（非加载中、无候选、无错误）。 */
  get empty(): boolean {
    return !this.loading && this.errorCode === undefined && this.items.length === 0
  }

  /** 是否部门类型。 */
  get isDeptKind(): boolean {
    return this.kind === 'dept'
  }

  /** 选中标识（受控值归一）。 */
  get selectedIds(): string[] {
    return normalizeOrgIds(this.value, this.multiple)
  }

  /** 选中项（未解析项以标识占位，回显不丢值）。 */
  get selectedItems(): OrgOptionItem[] {
    return this.selectedIds.map((id) => this.itemOf(id) ?? this.placeholderOf(id))
  }

  /** 是否可发起候选加载（就绪 ∧ 数据源对应方法存在）。 */
  get canLoad(): boolean {
    if (!this.ready || this.source === undefined) {
      return false
    }
    if (this.kind === 'dept') {
      return typeof this.source.loadDeptTree === 'function'
    }
    return this.kind === 'user'
      ? typeof this.source.searchUsers === 'function'
      : typeof this.source.searchPosts === 'function'
  }

  /** 是否可发起批量回显（就绪 ∧ 数据源支持 ∧ 有选中值）。 */
  get canResolve(): boolean {
    return (
      this.ready &&
      this.selectedIds.length > 0 &&
      typeof this.source?.resolveNames === 'function'
    )
  }

  /**
   * 注入 / 移除组织数据源（移除即回落占位零请求）。
   *
   * @param source 数据源适配器；`undefined` 表示移除。
   */
  setSource(source: OrgSourceAdapter | undefined): void {
    this.source = source
    this.emitUpdate()
  }

  /**
   * 注入 / 移除用户展示能力。
   *
   * @param display 用户展示能力；`undefined` 表示移除。
   */
  setUserDisplay(display: BaseUserDisplay | undefined): void {
    this.userDisplay = display
    this.syncUserDisplay()
    this.emitUpdate()
  }

  /**
   * 切换对象类型（清空候选 / 关键词 / 缓存；部门树保留）。
   *
   * @param kind 对象类型。
   */
  setKind(kind: OrgKind): void {
    this.kind = kind
    this.keyword = ''
    this.page = 1
    this.total = 0
    this.limitExceeded = false
    this.errorCode = undefined
    this.errorMessage = ''
    this.#cache.clear()
    this.items.splice(0, this.items.length)
    this.options.splice(0, this.options.length)
    this.emitUpdate()
  }

  /**
   * 设置关键词（归一后写入；防抖与请求由调用方 / 件层调度）。
   *
   * @param keyword 关键词。
   */
  setKeyword(keyword: string): void {
    this.keyword = normalizeOrgKeyword(keyword)
    this.page = 1
    this.emitUpdate()
  }

  /**
   * 设置部门过滤（清空候选缓存，不自行取数）。
   *
   * @param deptId 部门标识（空串取消过滤）。
   * @param includeChildren 是否含下级。
   */
  setDeptFilter(deptId: string, includeChildren = false): void {
    this.deptId = deptId.trim()
    this.includeChildren = includeChildren
    this.page = 1
    this.#cache.clear()
    this.emitUpdate()
  }

  /**
   * 设置状态过滤（清空候选缓存，不自行取数）。
   *
   * @param status 状态（空串不限定）。
   */
  setStatus(status: OrgStatus | ''): void {
    this.status = status
    this.page = 1
    this.#cache.clear()
    this.emitUpdate()
  }

  /**
   * 设置多选（受控值按新口径归一）。
   *
   * @param value 是否多选。
   */
  setMultiple(value: boolean): void {
    this.multiple = value
    const ids = normalizeOrgIds(this.value, value)
    this.setValue(value ? ids : ids[0])
    this.emitUpdate()
  }

  /**
   * 设置多选上限（非法回落 0 不限）。
   *
   * @param limit 上限。
   */
  setLimit(limit: number): void {
    this.limit = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : ORG_LIMIT_DEFAULT
    this.emitUpdate()
  }

  /**
   * 设置候选页码（夹取；不自行取数）。
   *
   * @param page 页码。
   */
  setPage(page: number): void {
    this.page = clampOrgPage(page)
    this.emitUpdate()
  }

  /**
   * 设置多选超限标记（件层按受控控件选择结果同步）。
   *
   * @param value 是否超限。
   */
  setLimitExceeded(value: boolean): void {
    if (this.limitExceeded === value) {
      return
    }
    this.limitExceeded = value
    this.emitUpdate()
  }

  /**
   * 选中 / 取消选中（多选增删去重并按上限截断；单选整体替换）。
   *
   * @param id 标识。
   */
  toggle(id: string): void {
    if (!this.multiple) {
      if (this.selectedIds[0] === id) {
        return
      }
      this.setValue(id)
      this.emitUpdate()
      return
    }
    const current = this.selectedIds
    if (current.includes(id)) {
      this.setValue(removeOrgId(current, id))
      this.limitExceeded = false
      this.emitUpdate()
      return
    }
    const result = applyOrgSelection(current, [id], { multiple: true, limit: this.limit })
    this.limitExceeded = result.exceeded
    this.setValue(result.ids)
    this.emitUpdate()
  }

  /**
   * 移除选中项。
   *
   * @param id 标识。
   */
  remove(id: string): void {
    const ids = removeOrgId(this.selectedIds, id)
    this.limitExceeded = false
    this.setValue(this.multiple ? ids : ids[0])
    this.emitUpdate()
  }

  /** 清空选中。 */
  clearSelection(): void {
    this.limitExceeded = false
    this.setValue(undefined)
    this.emitUpdate()
  }

  /**
   * 加载候选（kind 派发：用户 / 岗位查询、部门树；缓存命中不请求）。
   *
   * @returns 无。
   */
  override async load(): Promise<void> {
    if (this.kind === 'dept') {
      await this.loadDeptTree()
      return
    }
    const source = this.source
    if (!this.canLoad || source === undefined) {
      return
    }
    const query = this.searchQuery()
    const cacheKey = orgCacheKey(this.kind, query)
    const cached = this.#cache.get(cacheKey)
    if (cached !== undefined) {
      this.applyCandidates(cached)
      this.syncUserDisplay()
      this.emitUpdate()
      return
    }
    const token = (this.#listSeq += 1)
    this.markLoaded()
    this.loading = true
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw =
        this.kind === 'user'
          ? await source.searchUsers?.(query as OrgUserQuery)
          : await source.searchPosts?.(query as OrgPostQuery)
      if (token !== this.#listSeq) {
        return
      }
      const page = parseOrgPage(raw, this.kind)
      this.total = page.total
      this.cacheSet(cacheKey, page.items)
      this.applyCandidates(page.items)
      this.syncUserDisplay()
      this.loading = false
      this.errorCode = undefined
      this.errorMessage = ''
      this.emitUpdate()
    } catch (error) {
      if (token !== this.#listSeq) {
        return
      }
      this.loading = false
      this.applyError(error, 'BaseOrgSelect.load')
      this.emitUpdate()
    }
  }

  /**
   * 按 id 批量回显（单次批量出口，避免 N+1；已解析项常驻内存不重复请求）。
   *
   * @param ids 待回显标识（缺省取当前选中值）。
   * @returns 无。
   */
  async resolve(ids?: readonly string[]): Promise<void> {
    const source = this.source
    const targets = normalizeOrgIds(ids ?? this.selectedIds, true)
    if (
      !this.ready ||
      source === undefined ||
      typeof source.resolveNames !== 'function' ||
      targets.length === 0
    ) {
      return
    }
    const pending = targets.filter((id) => findOrgItem(this.items, id) === undefined)
    if (pending.length === 0) {
      return
    }
    const token = (this.#resolveSeq += 1)
    this.markLoaded()
    this.loading = true
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw = await source.resolveNames({ target: this.kind, ids: pending })
      if (token !== this.#resolveSeq) {
        return
      }
      const refs = normalizeOrgNameRefs(raw, this.kind)
      this.applyItems(refs)
      this.syncUserDisplay()
      this.loading = false
      this.emitUpdate()
    } catch (error) {
      if (token !== this.#resolveSeq) {
        return
      }
      this.loading = false
      this.applyError(error, 'BaseOrgSelect.resolve')
      this.emitUpdate()
    }
  }

  /**
   * 加载部门树（一次性返回、不分页；会话缓存，重复调用不请求）。
   *
   * @returns 无。
   */
  async loadDeptTree(): Promise<void> {
    const source = this.source
    if (!this.ready || source === undefined || typeof source.loadDeptTree !== 'function') {
      return
    }
    if (this.#deptLoaded) {
      return
    }
    const token = (this.#treeSeq += 1)
    this.markLoaded()
    this.loading = true
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw = await source.loadDeptTree({ status: this.status })
      if (token !== this.#treeSeq) {
        return
      }
      const nodes = parseOrgDeptTree(raw)
      this.deptNodes.splice(0, this.deptNodes.length, ...nodes)
      this.#deptLoaded = true
      this.applyItems([...this.items])
      this.syncUserDisplay()
      this.loading = false
      this.emitUpdate()
    } catch (error) {
      if (token !== this.#treeSeq) {
        return
      }
      this.loading = false
      this.applyError(error, 'BaseOrgSelect.loadDeptTree')
      this.emitUpdate()
    }
  }

  /**
   * 按标识取选项（未解析返回 `undefined`）。
   *
   * @param id 标识。
   */
  itemOf(id: string): OrgOptionItem | undefined {
    return findOrgItem(this.items, id)
  }

  /**
   * 按标识取展示文案（未解析回退标识）。
   *
   * @param id 标识。
   */
  labelOf(id: string): string {
    const item = this.itemOf(id)
    return item === undefined ? id : orgItemLabel(item)
  }

  /** 选中回显文本（「、」连接；空值「—」）。 */
  selectionText(): string {
    const items = this.selectedItems
    return items.length === 0 ? ORG_EMPTY_VALUE : orgSelectionText(items)
  }

  /**
   * 选中标签摘要（超过阈值折叠）。
   *
   * @param maxVisible 可见上限（缺省按默认折叠阈值）。
   */
  tagSummary(maxVisible?: number): OrgTagSummary {
    return orgTagSummary(this.selectedItems, maxVisible)
  }

  /** 多选上限提示文案。 */
  limitText(): string {
    return orgLimitText(this.kind, this.limit)
  }

  /**
   * 失效缓存（数据变更 / 切换条件后调用）。
   *
   * @param kind 指定 `dept` 时另清部门树；缺省仅清候选缓存。
   */
  invalidate(kind?: OrgKind): void {
    this.#cache.clear()
    if (kind === undefined || kind === 'dept') {
      this.deptNodes.splice(0, this.deptNodes.length)
      this.#deptLoaded = false
    }
    this.emitUpdate()
  }

  /**
   * 按值回显文案（数组 → 「、」连接；未解析回退标识）。
   *
   * @param value 值（单值 / 数组）。
   */
  override getLabel(value: string | string[]): string | undefined {
    const ids = normalizeOrgIds(value, true)
    if (ids.length === 0) {
      return undefined
    }
    if (Array.isArray(value)) {
      return ids.map((id) => this.labelOf(id)).join('、')
    }
    return this.labelOf(ids[0] as string)
  }

  /** 用具类型时把选项汇入用户展示花名册。 */
  syncUserDisplay(): void {
    if (this.kind !== 'user' || this.userDisplay === undefined) {
      return
    }
    this.userDisplay.mergeUsers(this.items.map((item) => this.toDisplayInfo(item)))
  }

  /** 当前归一化查询。 */
  searchQuery(): OrgSearchQuery {
    return normalizeOrgSearchQuery({
      kind: this.kind,
      keyword: this.keyword,
      deptId: this.deptId,
      includeChildren: this.includeChildren,
      status: this.status,
      page: this.page,
      pageSize: ORG_DEFAULT_PAGE_SIZE,
    })
  }

  /** 当前批量回显参数（与后端出口同源）。 */
  resolveParams(ids?: readonly string[]): Record<string, unknown> {
    return buildOrgResolveQuery(this.kind, ids ?? this.selectedIds)
  }

  /**
   * 未解析项的展示占位（名称留空 → 展示回退标识）。
   *
   * @param id 标识。
   */
  private placeholderOf(id: string): OrgOptionItem {
    return { id, name: '', kind: this.kind, status: 'enabled', deleted: false }
  }

  /**
   * 选项 → 用户展示信息（状态映射 `enabled → active` / `disabled → disabled`）。
   *
   * @param item 选项。
   */
  private toDisplayInfo(item: OrgOptionItem): UserDisplayInfo {
    return {
      id: item.id,
      name: item.name === '' ? item.id : item.name,
      avatar: item.avatar,
      status: item.deleted ? undefined : item.status === 'disabled' ? 'disabled' : 'active',
      deptPath: item.deptPath,
      deleted: item.deleted,
    }
  }

  /**
   * 补全部门路径（已加载部门树且选项含归属部门时）。
   *
   * @param item 选项。
   */
  private withDeptPath(item: OrgOptionItem): OrgOptionItem {
    if (item.deptPath !== undefined || item.deptId === undefined || this.deptNodes.length === 0) {
      return item
    }
    const path = findOrgDeptPath(this.deptNodes, item.deptId)
    return path.length === 0 ? item : { ...item, deptPath: path.join(' / ') }
  }

  /**
   * 替换候选（已选项常驻；同步 `options` 与数据版本）。
   *
   * @param candidates 候选列表。
   */
  private applyCandidates(candidates: readonly OrgOptionItem[]): void {
    const keep = this.selectedItems.filter((item) => findOrgItem(candidates, item.id) === undefined)
    this.applyItems(mergeOrgItems(keep, candidates))
  }

  /**
   * 并入选项池（同步 `options` 与数据版本）。
   *
   * @param incoming 增量列表。
   */
  private applyItems(incoming: readonly OrgOptionItem[]): void {
    const next = mergeOrgItems(this.items, incoming.map((item) => this.withDeptPath(item)))
    this.items.splice(0, this.items.length, ...next)
    this.options.splice(
      0,
      this.options.length,
      ...next.map((item) => ({ value: item.id, label: orgItemLabel(item) })),
    )
    this.dataVersion += 1
  }

  /**
   * 写入关键词结果短缓存（超出上限按最早写入淘汰）。
   *
   * @param key 缓存键。
   * @param items 候选列表。
   */
  private cacheSet(key: string, items: readonly OrgOptionItem[]): void {
    if (this.#cache.has(key)) {
      this.#cache.delete(key)
    }
    this.#cache.set(key, items.map((item) => ({ ...item })))
    while (this.#cache.size > ORG_CACHE_MAX) {
      const oldest = this.#cache.keys().next().value
      if (oldest === undefined) {
        break
      }
      this.#cache.delete(oldest)
    }
  }

  /**
   * 应用错误（错误码文案优先，回落加载失败文案）。
   *
   * @param error 原始错误。
   * @param scope 上报域。
   */
  private applyError(error: unknown, scope: string): void {
    this.errorCode = readErrorCode(error)
    this.errorMessage = isOrgErrorCode(this.errorCode)
      ? resolveOrgErrorText(this.errorCode)
      : ORG_LOAD_ERROR_TEXT
    this.reportError(error, { scope })
  }

  /** 广播更新（已释放则忽略）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
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
