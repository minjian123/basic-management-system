/**
 * 字典缓存能力基类 `BaseDictStore`：全局一份缓存（跨件 / 跨表单共享）——
 * 版本比对、批量合并（同批多类型一次请求）、同类型并发去重、大小字典缓存、
 * 按条目 id 子集回填（批量翻译防 N+1）、本地二次缓存（经注入式通道，核心不触浏览器 API）。
 *
 * 继承链：`BaseComponent`（组件根）→ `BaseDictStore`（能力基类，旁挂注入）；
 * 由 `BaseDictSelect` 与翻译器经**注入引用**共用（同 `BaseUserDisplay` 模式）。
 * 未就绪 / 未注入数据源即占位零请求（`requestCount` 恒 0）。
 */

import { BasePlaceholderState } from './placeholder-state'
import {
  DICT_CACHE_MAX,
  DICT_DEFAULT_LOCALE,
  DICT_PROBE_LIMIT,
  DICT_STORAGE_MAX_BYTES,
  DICT_SUBSET_MAX,
  dictCacheKey,
  dictStorageKey,
  dictSubsetKey,
  isLargeDict,
  normalizeDictBatchResult,
  normalizeDictItems,
  normalizeDictTypeResult,
  type DictBatchResult,
  type DictItem,
  type DictTypeResult,
} from '../domain/dict'
import type { DictSourceAdapter } from './dict-source'

/** 本地二次缓存通道（浏览器 `localStorage` 经注入接入，核心不触浏览器 API）。 */
export interface DictStorageChannel {
  /** 读字符串（不可用返回 `undefined`）。 */
  read(key: string): string | undefined
  /** 写字符串（失败静默）。 */
  write(key: string, value: string): void
  /** 删键。 */
  remove(key: string): void
}

/** 类型缓存项。 */
export interface DictCacheEntry {
  /** 记录时捕获的版本号。 */
  version: number
  /** 条目集（已加载）。 */
  items: DictItem[]
  /** 是否还有更多（探针截断）。 */
  hasMore: boolean
  /** 命中总数。 */
  total: number
}

/** 批量取数回调（由投影经数据源接线；返回 `undefined` 表示未覆写）。 */
export type DictBatchLoader = (
  types: readonly string[],
  version: number | undefined,
) => Promise<DictBatchResult | undefined>

/** 单类型取数回调。 */
export type DictTypeLoader = (query: {
  dataSourceKey: string
  version?: number
  keyword?: string
  parentId?: string
  ids?: readonly string[]
  limit?: number
}) => Promise<DictTypeResult | undefined>

/** 子集取数回调（按条目 id 批量回填）。 */
export type DictSubsetLoader = (dataSourceKey: string, ids: readonly string[]) => Promise<DictItem[] | undefined>

/** 字典缓存能力基类（抽象；全局一份缓存，跨件 / 跨表单共享）。 */
export abstract class BaseDictStore extends BasePlaceholderState {
  /** 能力键。 */
  readonly identifier: string = 'dict_store'
  /** 依赖登记。 */
  override readonly depends = ['placeholder_state']
  /** 数据通路是否就绪（占位语义，缺省未就绪）。 */
  ready = false
  /** 语言（变更清空缓存）。 */
  locale: string = DICT_DEFAULT_LOCALE
  /** 最近一次字典数据版本号（全局，后端下发）。 */
  dictVersion = 0
  /** 注入式数据源（未注入即占位零请求）。 */
  source: DictSourceAdapter | undefined
  /** 本地二次缓存通道（未注入即不持久化）。 */
  storage: DictStorageChannel | undefined

  /** 类型缓存（LRU：Map 插入序即访问序）。 */
  readonly _entries = new Map<string, DictCacheEntry>()
  /** 子集 label 缓存（`{locale}:{type}:{id}` → label）。 */
  readonly _subsets = new Map<string, string>()
  /** 大字典类型登记（探针判定）。 */
  readonly _large = new Set<string>()
  /** 已解析 id 登记（含未命中；避免重复请求，未命中仍不占位）。 */
  readonly _resolved = new Set<string>()
  /** 在途类型请求（并发去重）。 */
  readonly _pending = new Map<string, Promise<void>>()
  /** 批量窗口队列。 */
  _batchQueue: string[] = []
  /** 批量窗口在途。 */
  _batchWait: Promise<void> | undefined
  /** 单类型取数回调（投影接线）。 */
  _typeLoader: DictTypeLoader | undefined
  /** 批量取数回调。 */
  _batchLoader: DictBatchLoader | undefined
  /** 子集取数回调。 */
  _subsetLoader: DictSubsetLoader | undefined

  /** 已加载类型（快照）。 */
  get loadedTypes(): string[] {
    return [...this._entries.keys()].map((key) => key.split(':').slice(1).join(':'))
  }

  /** 大字典类型（探针判定；快照）。 */
  get largeTypes(): string[] {
    return [...this._large]
  }

  /** 类型缓存条数。 */
  get cacheSize(): number {
    return this._entries.size
  }

  /** 子集缓存条数。 */
  get subsetSize(): number {
    return this._subsets.size
  }

  /**
   * 切换语言（清空类型 / 子集缓存；本地缓存按新键读取）。
   *
   * @param locale 语言。
   */
  setLocale(locale: string): void {
    if (this.locale === locale) {
      return
    }
    this.locale = locale
    this._entries.clear()
    this._subsets.clear()
    this._large.clear()
    this._resolved.clear()
    this.emitUpdate()
  }

  /**
   * 注入 / 移除数据源（移除即回落占位零请求）。
   *
   * @param source 数据源适配器；`undefined` 表示移除。
   */
  setSource(source: DictSourceAdapter | undefined): void {
    this.source = source
    this.emitUpdate()
  }

  /**
   * 注入 / 移除本地二次缓存通道。
   *
   * @param channel 通道；`undefined` 表示移除。
   */
  setStorage(channel: DictStorageChannel | undefined): void {
    this.storage = channel
    this.emitUpdate()
  }

  /**
   * 绑定批量取数回调（投影接线）。
   *
   * @param loader 回调。
   */
  bindBatchLoader(loader: DictBatchLoader): void {
    this._batchLoader = loader
  }

  /**
   * 绑定单类型取数回调。
   *
   * @param loader 回调。
   */
  bindTypeLoader(loader: DictTypeLoader): void {
    this._typeLoader = loader
  }

  /**
   * 绑定子集取数回调。
   *
   * @param loader 回调。
   */
  bindSubsetLoader(loader: DictSubsetLoader): void {
    this._subsetLoader = loader
  }

  /**
   * 批量确保类型已加载（同批多类型合并为一次 `batch` 请求；已加载 / 在途去重）。
   *
   * @param types 类型序列。
   * @returns 无。
   */
  async ensureTypes(types: readonly string[]): Promise<void> {
    if (!this.canRequest()) {
      return
    }
    const pending: string[] = []
    for (const type of types) {
      if (type === '' || this.isLoaded(type) || this._pending.has(type) || this._batchQueue.includes(type)) {
        continue
      }
      pending.push(type)
    }
    if (pending.length === 0) {
      return
    }
    await this._scheduleBatch(pending)
  }

  /**
   * 确保单类型已加载（探针 `limit=2001` 判定大小字典；本地缓存命中先显示、版本校验后刷新）。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 无。
   */
  async ensureType(dataSourceKey: string): Promise<void> {
    if (dataSourceKey === '' || this.isLoaded(dataSourceKey)) {
      return
    }
    const inflight = this._pending.get(dataSourceKey)
    if (inflight !== undefined) {
      return inflight
    }
    if (!this.canRequest() || this._typeLoader === undefined) {
      return
    }
    const task = this._loadOne(dataSourceKey)
    this._pending.set(dataSourceKey, task)
    try {
      await task
    } finally {
      this._pending.delete(dataSourceKey)
    }
  }

  /**
   * 远程搜索（关键字；结果仅作候选，不写类型缓存）。
   *
   * @param dataSourceKey 字典类型码。
   * @param keyword 关键字。
   * @returns 候选条目（未就绪 / 未注入返回空）。
   */
  async searchRemote(dataSourceKey: string, keyword: string): Promise<DictItem[]> {
    if (!this.canRequest() || this._typeLoader === undefined || dataSourceKey === '') {
      return []
    }
    this.markLoaded()
    this.loading = true
    this.emitUpdate()
    try {
      const result = await this._typeLoader({ dataSourceKey, keyword, limit: DICT_PROBE_LIMIT })
      this.loading = false
      this.emitUpdate()
      if (result === undefined) {
        return []
      }
      return result.items ?? []
    } catch (error) {
      this.loading = false
      this.reportError(error, { scope: 'BaseDictStore.searchRemote' })
      this.emitUpdate()
      return []
    }
  }

  /**
   * 按条目 id 批量回显（缺失 id 一次 `ids=` 子集回填；二次零请求）。
   *
   * @param dataSourceKey 字典类型码。
   * @param ids 待回显条目 id 序列。
   * @returns 无。
   */
  async resolveIds(dataSourceKey: string, ids: readonly string[]): Promise<void> {
    const targets = [...new Set(ids)].filter(
      (id) => id !== '' && !this._resolved.has(dictSubsetKey(this.locale, dataSourceKey, id)),
    )
    if (targets.length === 0) {
      return
    }
    for (const id of targets) {
      this._resolved.add(dictSubsetKey(this.locale, dataSourceKey, id))
    }
    if (!this.canRequest()) {
      return
    }
    if (this._subsetLoader !== undefined) {
      this.markLoaded()
      this.loading = true
      this.emitUpdate()
      try {
        const items = await this._subsetLoader(dataSourceKey, targets)
        this.loading = false
        if (items !== undefined && items.length > 0) {
          this._putSubset(dataSourceKey, items)
          this._mergeEntry(dataSourceKey, items)
        }
        this.emitUpdate()
      } catch (error) {
        this.loading = false
        this.reportError(error, { scope: 'BaseDictStore.resolveIds' })
        this.emitUpdate()
      }
      return
    }
    if (this._typeLoader !== undefined) {
      this.markLoaded()
      const result = await this._typeLoader({ dataSourceKey, ids: targets, limit: DICT_PROBE_LIMIT })
      if (result !== undefined && result.items !== null) {
        this._putSubset(dataSourceKey, result.items)
        this._mergeEntry(dataSourceKey, result.items)
        this.emitUpdate()
      }
    }
  }

  /**
   * 同步读类型条目（未加载返回空数组）。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 条目列表。
   */
  itemsOf(dataSourceKey: string): DictItem[] {
    return this._entries.get(this._key(dataSourceKey))?.items ?? []
  }

  /**
   * 取类型缓存项（未加载返回 `undefined`）。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 缓存项。
   */
  entryOf(dataSourceKey: string): DictCacheEntry | undefined {
    return this._entries.get(this._key(dataSourceKey))
  }

  /**
   * 类型是否已加载。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 已加载 `true`。
   */
  isLoaded(dataSourceKey: string): boolean {
    return this._entries.has(this._key(dataSourceKey))
  }

  /**
   * 是否超大字典（探针判定）。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 超大字典 `true`。
   */
  isLarge(dataSourceKey: string): boolean {
    return this._large.has(dataSourceKey)
  }

  /**
   * 按条目 id 取标签（子集缓存优先，其次类型缓存；未命中 `undefined`）。
   *
   * @param dataSourceKey 字典类型码。
   * @param id 条目 id。
   * @returns 标签；未命中 `undefined`。
   */
  labelOf(dataSourceKey: string, id: string): string | undefined {
    const subset = this._subsets.get(dictSubsetKey(this.locale, dataSourceKey, id))
    if (subset !== undefined) {
      return subset
    }
    return this._entries.get(this._key(dataSourceKey))?.items.find((item) => item.id === id)?.label
  }

  /**
   * 失效缓存（类型 / 全部；同步清本地二次缓存）。
   *
   * @param dataSourceKey 字典类型码；缺省全清。
   */
  invalidate(dataSourceKey?: string): void {
    if (dataSourceKey === undefined) {
      for (const key of this._entries.keys()) {
        this._removeLocal(key.split(':').slice(1).join(':'))
      }
      this._entries.clear()
      this._subsets.clear()
      this._large.clear()
      this._resolved.clear()
      this.emitUpdate()
      return
    }
    this._entries.delete(this._key(dataSourceKey))
    for (const key of [...this._resolved]) {
      if (key.startsWith(`${this.locale}:${dataSourceKey}:`)) {
        this._resolved.delete(key)
      }
    }
    for (const key of [...this._subsets.keys()]) {
      if (key.startsWith(`${this.locale}:${dataSourceKey}:`)) {
        this._subsets.delete(key)
      }
    }
    this._large.delete(dataSourceKey)
    this._removeLocal(dataSourceKey)
    this.emitUpdate()
  }

  /**
   * 预加载（宿主登录后调用；等价 `ensureTypes`）。
   *
   * @param types 类型序列。
   * @returns 无。
   */
  async preload(types: readonly string[]): Promise<void> {
    await this.ensureTypes(types)
  }

  /**
   * 是否可发起请求（就绪 ∧ 数据源注入）。
   *
   * @returns 可请求 `true`。
   */
  private canRequest(): boolean {
    return this.ready && this.source !== undefined
  }

  /** 广播更新（已释放则忽略）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 缓存键（`{locale}:{type}`）。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 缓存键。
   */
  _key(dataSourceKey: string): string {
    return dictCacheKey(this.locale, dataSourceKey)
  }

  /**
   * 单类型加载（本地缓存先显示 → 版本校验请求）。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 无。
   */
  async _loadOne(dataSourceKey: string): Promise<void> {
    const local = this._readLocal(dataSourceKey)
    if (local !== undefined) {
      this._putEntry(dataSourceKey, local)
      if (local.hasMore) {
        this._large.add(dataSourceKey)
      }
    }
    this.markLoaded()
    this.loading = true
    this.emitUpdate()
    try {
      const result = await (this._typeLoader as DictTypeLoader)({
        dataSourceKey,
        version: this._entries.get(this._key(dataSourceKey))?.version,
        limit: DICT_PROBE_LIMIT,
      })
      this.loading = false
      if (result === undefined) {
        this.emitUpdate()
        return
      }
      if (result.items === null) {
        // 版本一致：保留本地缓存（无缓存时以空集标记已加载）
        if (!this._entries.has(this._key(dataSourceKey))) {
          this._putEntry(dataSourceKey, { version: result.version, items: [], hasMore: false, total: 0 })
        }
        this.dictVersion = result.version
        this.emitUpdate()
        return
      }
      this.dictVersion = result.version
      this._putEntry(dataSourceKey, {
        version: result.version,
        items: result.items,
        hasMore: result.hasMore,
        total: result.total,
      })
      if (isLargeDict(result)) {
        this._large.add(dataSourceKey)
      }
      this.emitUpdate()
    } catch (error) {
      this.loading = false
      this.reportError(error, { scope: 'BaseDictStore.ensureType' })
      this.emitUpdate()
    }
  }

  /**
   * 批量窗口调度（同微任务批次内多类型合并为一次请求）。
   *
   * @param types 类型序列。
   * @returns 批次完成。
   */
  _scheduleBatch(types: readonly string[]): Promise<void> {
    for (const type of types) {
      if (!this._batchQueue.includes(type)) {
        this._batchQueue.push(type)
      }
    }
    if (this._batchWait === undefined) {
      this._batchWait = Promise.resolve().then(async () => {
        const batch = [...this._batchQueue]
        this._batchQueue = []
        this._batchWait = undefined
        await this._flushBatch(batch)
      })
    }
    return this._batchWait
  }

  /**
   * 执行批量取数（本地缓存先显示 → 一次 `batch` 请求）。
   *
   * @param types 类型序列。
   * @returns 无。
   */
  async _flushBatch(types: readonly string[]): Promise<void> {
    if (!this.canRequest() || this._batchLoader === undefined) {
      return
    }
    const targets: string[] = []
    for (const type of types) {
      if (type === '' || this.isLoaded(type)) {
        continue
      }
      const local = this._readLocal(type)
      if (local !== undefined) {
        this._putEntry(type, local)
        if (local.hasMore) {
          this._large.add(type)
        }
      }
      targets.push(type)
    }
    if (targets.length === 0) {
      this.emitUpdate()
      return
    }
    this.markLoaded()
    this.loading = true
    this.emitUpdate()
    try {
      const result = await (this._batchLoader as DictBatchLoader)(targets, this.dictVersion || undefined)
      this.loading = false
      if (result === undefined) {
        this.emitUpdate()
        return
      }
      this.dictVersion = result.version
      for (const type of targets) {
        const entry = result.items[type]
        if (entry === null || entry === undefined) {
          if (!this._entries.has(this._key(type))) {
            this._putEntry(type, { version: result.version, items: [], hasMore: false, total: 0 })
          }
          continue
        }
        if (entry.items === null) {
          continue
        }
        this._putEntry(type, {
          version: entry.version,
          items: entry.items,
          hasMore: entry.hasMore,
          total: entry.total,
        })
        if (isLargeDict(entry)) {
          this._large.add(type)
        }
      }
      this.emitUpdate()
    } catch (error) {
      this.loading = false
      this.reportError(error, { scope: 'BaseDictStore.ensureTypes' })
      this.emitUpdate()
    }
  }

  /**
   * 写入类型缓存（LRU 淘汰 + 本地二次缓存）。
   *
   * @param dataSourceKey 字典类型码。
   * @param entry 缓存项。
   */
  _putEntry(dataSourceKey: string, entry: DictCacheEntry): void {
    const key = this._key(dataSourceKey)
    if (this._entries.has(key)) {
      this._entries.delete(key)
    }
    this._entries.set(key, entry)
    while (this._entries.size > DICT_CACHE_MAX) {
      const oldest = this._entries.keys().next().value
      if (oldest === undefined) {
        break
      }
      const type = oldest.split(':').slice(1).join(':')
      this._entries.delete(oldest)
      this._removeLocal(type)
    }
    if (!this._large.has(dataSourceKey)) {
      this._writeLocal(dataSourceKey, entry)
    }
  }

  /**
   * 子集条目合并进类型缓存（已加载时；不新建缓存项）。
   *
   * @param dataSourceKey 字典类型码。
   * @param items 条目列表。
   */
  _mergeEntry(dataSourceKey: string, items: readonly DictItem[]): void {
    const entry = this._entries.get(this._key(dataSourceKey))
    if (entry === undefined) {
      return
    }
    const merged = [...entry.items]
    for (const item of items) {
      const index = merged.findIndex((existing) => existing.id === item.id)
      if (index >= 0) {
        merged[index] = item
      } else {
        merged.push(item)
      }
    }
    entry.items = merged
  }

  /**
   * 写子集缓存（LRU 淘汰）。
   *
   * @param dataSourceKey 字典类型码。
   * @param items 条目列表。
   */
  _putSubset(dataSourceKey: string, items: readonly DictItem[]): void {
    for (const item of items) {
      const key = dictSubsetKey(this.locale, dataSourceKey, item.id)
      if (this._subsets.has(key)) {
        this._subsets.delete(key)
      }
      this._subsets.set(key, item.label)
      while (this._subsets.size > DICT_SUBSET_MAX) {
        const oldest = this._subsets.keys().next().value
        if (oldest === undefined) {
          break
        }
        this._subsets.delete(oldest)
      }
    }
  }

  /**
   * 读本地二次缓存（解析失败 / 结构非法返回 `undefined`）。
   *
   * @param dataSourceKey 字典类型码。
   * @returns 缓存项。
   */
  _readLocal(dataSourceKey: string): DictCacheEntry | undefined {
    const raw = this.storage?.read(dictStorageKey(this.locale, dataSourceKey))
    if (raw === undefined) {
      return undefined
    }
    try {
      const parsed = JSON.parse(raw) as { version?: unknown; items?: unknown; hasMore?: unknown; total?: unknown }
      const items = normalizeDictItems(parsed.items)
      if (items.length === 0) {
        return undefined
      }
      return {
        version: typeof parsed.version === 'number' ? parsed.version : 0,
        items,
        hasMore: parsed.hasMore === true,
        total: typeof parsed.total === 'number' ? parsed.total : items.length,
      }
    } catch {
      return undefined
    }
  }

  /**
   * 写本地二次缓存（小字典；超体积不写；失败静默）。
   *
   * @param dataSourceKey 字典类型码。
   * @param entry 缓存项。
   */
  _writeLocal(dataSourceKey: string, entry: DictCacheEntry): void {
    if (this.storage === undefined || this._large.has(dataSourceKey)) {
      return
    }
    const payload = JSON.stringify({
      version: entry.version,
      items: entry.items,
      hasMore: entry.hasMore,
      total: entry.total,
    })
    if (payload.length > DICT_STORAGE_MAX_BYTES) {
      return
    }
    this.storage.write(dictStorageKey(this.locale, dataSourceKey), payload)
  }

  /**
   * 删本地二次缓存。
   *
   * @param dataSourceKey 字典类型码。
   */
  _removeLocal(dataSourceKey: string): void {
    this.storage?.remove(dictStorageKey(this.locale, dataSourceKey))
  }
}

/**
 * 把注入式数据源接到缓存能力（投影与契约适配共用；未注入即解绑）。
 *
 * @param store 缓存能力实例。
 * @param source 数据源适配器；`undefined` 表示解绑。
 */
export function bindDictStoreSource(store: BaseDictStore, source: DictSourceAdapter | undefined): void {
  store.setSource(source)
  if (source === undefined) {
    return
  }
  const getType = source.getType
  const batch = source.batch
  if (getType !== undefined) {
    store.bindTypeLoader(async (query) =>
      normalizeDictTypeResult(
        await getType.call(source, {
          dataSourceKey: query.dataSourceKey,
          version: query.version,
          keyword: query.keyword,
          parentId: query.parentId,
          ids: query.ids,
          limit: query.limit,
        }),
      ),
    )
    store.bindSubsetLoader(async (dataSourceKey, ids) => {
      const result = normalizeDictTypeResult(await getType.call(source, { dataSourceKey, ids }))
      return result.items ?? []
    })
  }
  if (batch !== undefined) {
    store.bindBatchLoader(async (types, version) =>
      normalizeDictBatchResult(await batch.call(source, { types, version, locale: store.locale })),
    )
  }
}
