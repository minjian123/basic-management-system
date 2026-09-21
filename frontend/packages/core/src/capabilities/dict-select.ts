/**
 * 字典选择族组件基类 `BaseDictSelect`：字典下拉语义（小字典本地全量 / 大字典远程搜索）、
 * 禁用项、级联父值、多选与上限、批量回显（`values` 子集一次回填）。
 *
 * 全链：`BaseComponent → BasePlaceholderState → BaseValue → BaseField → BaseOptionSource → BaseDictSelect → 具体件`。
 * 数据通路经注入式 `DictSourceAdapter`（未注入即占位零请求）；缓存经注入的 `BaseDictStore`（全局一份）；
 * 核心不依赖 Vue / DOM / 浏览器 API。
 */

import {
  DICT_JOIN,
  DICT_LIMIT_TEXT_PREFIX,
  DICT_PROBE_LIMIT,
  DICT_EMPTY_VALUE,
  filterDictItems,
  isBlankDictKeyword,
  isDictErrorCode,
  findDictItem,
  mergeDictItems,
  normalizeDictKeyword,
  normalizeDictTypeResult,
  normalizeDictValues,
  resolveDictErrorText,
  type DictItem,
} from '../domain/dict'
import { BaseOptionSource } from './option-source'
import type { BaseDictStore } from './dict-store'
import type { DictSourceAdapter } from './dict-source'

/** 字典选择族组件基类（抽象）。 */
export abstract class BaseDictSelect extends BaseOptionSource<string | string[]> {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'dict-select'
  /** 依赖登记。 */
  override readonly depends = ['option-source', 'dict-store']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 字典类型码。 */
  dictType = ''
  /** 搜索关键词。 */
  keyword = ''
  /** 级联父值（空串 = 顶层）。 */
  parentId = ''
  /** 是否多选。 */
  multiple = false
  /** 多选上限（0 不限）。 */
  limit = 0
  /** 候选与回显条目（常驻内存，按 value 合并）。 */
  readonly items: DictItem[] = []
  /** 多选超限标记。 */
  limitExceeded = false
  /** 错误码。 */
  errorCode: number | undefined
  /** 错误文案。 */
  errorMessage = ''
  /** 候选加载态。 */
  loadingItems = false
  /** 字典数据源（注入式；未注入即占位零请求）。 */
  source: DictSourceAdapter | undefined
  /** 字典缓存能力（注入引用；全局一份）。 */
  store: BaseDictStore | undefined

  /** 候选请求序号（防旧响应覆盖）。 */
  #listSeq = 0
  /** 回显请求序号。 */
  #resolveSeq = 0

  /** 是否超大字典（缓存层探针判定）。 */
  get isLarge(): boolean {
    return this.store !== undefined && this.store.isLarge(this.dictType)
  }

  /** 选中值（受控值归一）。 */
  get selectedValues(): string[] {
    return normalizeDictValues(this.value, this.multiple)
  }

  /** 选中条目（未解析项以值占位，回显不丢值）。 */
  get selectedItems(): DictItem[] {
    return this.selectedValues.map((value) => this.itemOf(value) ?? this.placeholderOf(value))
  }

  /** 是否可发起候选加载（就绪 ∧ 类型非空 ∧ 数据源或缓存可用）。 */
  get canLoad(): boolean {
    if (!this.ready || this.dictType === '') {
      return false
    }
    return this.source !== undefined || this.store !== undefined
  }

  /** 是否错误态。 */
  get error(): boolean {
    return this.errorCode !== undefined
  }

  /** 是否空态（非加载中、无候选、无错误）。 */
  get empty(): boolean {
    return !this.loadingItems && this.errorCode === undefined && this.items.length === 0
  }

  /**
   * 注入 / 移除缓存能力。
   *
   * @param store 缓存实例；`undefined` 表示移除。
   */
  setStore(store: BaseDictStore | undefined): void {
    this.store = store
    this.syncStore()
  }

  /**
   * 注入 / 移除字典数据源（移除即回落占位零请求）。
   *
   * @param source 数据源适配器；`undefined` 表示移除。
   */
  setSource(source: DictSourceAdapter | undefined): void {
    this.source = source
    this.emitUpdate()
  }

  /**
   * 切换字典类型（清空候选 / 关键词 / 错误）。
   *
   * @param dictType 字典类型码。
   */
  setDictType(dictType: string): void {
    this.dictType = dictType.trim()
    this.keyword = ''
    this.limitExceeded = false
    this.errorCode = undefined
    this.errorMessage = ''
    this.items.splice(0, this.items.length)
    this.options.splice(0, this.options.length)
    this.emitUpdate()
  }

  /**
   * 设置关键词（归一后写入；远程搜索由件层防抖调度）。
   *
   * @param keyword 关键词。
   */
  setKeyword(keyword: string): void {
    this.keyword = normalizeDictKeyword(keyword)
    this.emitUpdate()
  }

  /**
   * 设置级联父值（父值变更清空受控值并重载候选）。
   *
   * @param parentId 父值（空串 = 顶层）。
   */
  setParent(parentId: string): void {
    const next = parentId.trim()
    if (this.parentId === next) {
      return
    }
    this.parentId = next
    this.setValue(undefined)
    this.limitExceeded = false
    this.items.splice(0, this.items.length)
    this.options.splice(0, this.options.length)
    this.emitUpdate()
  }

  /**
   * 设置多选（受控值按新口径归一）。
   *
   * @param value 是否多选。
   */
  setMultiple(value: boolean): void {
    this.multiple = value
    const values = normalizeDictValues(this.value, value)
    super.setValue(value ? (values.length > 0 ? values : undefined) : values[0])
    this.emitUpdate()
  }

  /**
   * 设置多选上限（非法回落 0 不限）。
   *
   * @param limit 上限。
   */
  setLimit(limit: number): void {
    this.limit = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : 0
    this.emitUpdate()
  }

  /**
   * 同步多选超限标记（件层按受控控件选择结果同步）。
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
   * 设置受控值（归一：单值 / 数组；空值剔除）。
   *
   * @param value 受控值。
   */
  override setValue(value: string | string[] | undefined): void {
    const values = normalizeDictValues(value, this.multiple)
    if (values.length === 0) {
      super.setValue(undefined)
      return
    }
    super.setValue(this.multiple ? values : (values[0] as string))
  }

  /**
   * 选中 / 取消选中（多选增删去重并按上限截断；单选整体替换）。
   *
   * @param value 条目值。
   */
  toggle(value: string): void {
    if (!this.multiple) {
      if (this.selectedValues[0] === value) {
        return
      }
      this.setValue(value)
      this.emitUpdate()
      return
    }
    const current = this.selectedValues
    if (current.includes(value)) {
      this.setValue(current.filter((entry) => entry !== value))
      this.limitExceeded = false
      this.emitUpdate()
      return
    }
    if (this.limit > 0 && current.length >= this.limit) {
      this.limitExceeded = true
      this.emitUpdate()
      return
    }
    this.setValue([...current, value])
    this.limitExceeded = false
    this.emitUpdate()
  }

  /**
   * 移除选中项。
   *
   * @param value 条目值。
   */
  remove(value: string): void {
    const values = this.selectedValues.filter((entry) => entry !== value)
    this.limitExceeded = false
    this.setValue(this.multiple ? values : values[0])
    this.emitUpdate()
  }

  /** 清空选中。 */
  clearSelection(): void {
    this.limitExceeded = false
    this.setValue(undefined)
    this.emitUpdate()
  }

  /**
   * 加载候选（缓存优先：小字典全量本地过滤 / 大字典远程搜索；缓存命中不请求）。
   *
   * @returns 无。
   */
  override async load(): Promise<void> {
    if (!this.ready || this.dictType === '') {
      return
    }
    if (this.store !== undefined && this.store.ready && this.store.source !== undefined && this.parentId === '') {
      await this.store.ensureType(this.dictType)
      if (this.store.isLarge(this.dictType) && !isBlankDictKeyword(this.keyword)) {
        const candidates = await this.store.searchRemote(this.dictType, this.keyword)
        this.#applyCandidates(candidates)
        return
      }
      this.#applyCandidates(this.#filterTopLevel(this.store.itemsOf(this.dictType)))
      return
    }
    const loader = this.source?.getType
    if (loader === undefined || this.source === undefined) {
      return
    }
    const token = (this.#listSeq += 1)
    this.markLoaded()
    this.loadingItems = true
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw = await loader.call(this.source, {
        dictType: this.dictType,
        keyword: isBlankDictKeyword(this.keyword) ? undefined : this.keyword,
        parentId: this.parentId,
        limit: DICT_PROBE_LIMIT,
      })
      if (token !== this.#listSeq) {
        return
      }
      const result = normalizeDictTypeResult(raw)
      this.loadingItems = false
      if (result.items !== null) {
        this.#applyCandidates(result.items)
      }
      this.emitUpdate()
    } catch (error) {
      if (token !== this.#listSeq) {
        return
      }
      this.loadingItems = false
      this.#applyError(error)
      this.emitUpdate()
    }
  }

  /**
   * 远程搜索（大字典；结果仅作候选，不写类型缓存）。
   *
   * @param keyword 关键词。
   * @returns 候选条目。
   */
  async searchRemote(keyword: string): Promise<DictItem[]> {
    if (!this.ready || this.dictType === '') {
      return []
    }
    this.setKeyword(keyword)
    if (this.store !== undefined && this.store.ready && this.store.source !== undefined) {
      const candidates = await this.store.searchRemote(this.dictType, this.keyword)
      this.#applyCandidates(candidates)
      return candidates
    }
    const loader = this.source?.getType
    if (loader === undefined || this.source === undefined) {
      return []
    }
    this.markLoaded()
    try {
      const raw = await loader.call(this.source, {
        dictType: this.dictType,
        keyword: isBlankDictKeyword(this.keyword) ? undefined : this.keyword,
        parentId: this.parentId,
        limit: DICT_PROBE_LIMIT,
      })
      const result = normalizeDictTypeResult(raw)
      const candidates = result.items ?? []
      this.#applyCandidates(candidates)
      return candidates
    } catch (error) {
      this.#applyError(error)
      this.emitUpdate()
      return []
    }
  }

  /**
   * 批量回显（已选值缺失项一次 `values=` 子集回填；已解析不重复请求）。
   *
   * @param extra 额外待回显值（缺省取当前选中值）。
   * @returns 无。
   */
  async resolve(extra?: readonly string[]): Promise<void> {
    const targets = normalizeDictValues(extra ?? this.selectedValues, true)
    if (!this.ready || this.dictType === '' || targets.length === 0) {
      return
    }
    const missing = targets.filter((value) => this.itemOf(value) === undefined)
    if (missing.length === 0) {
      return
    }
    if (this.store !== undefined && this.store.ready && this.store.source !== undefined) {
      await this.store.resolveValues(this.dictType, missing)
      this.#applyItems(
        missing.map((value) => {
          const label = this.store?.labelOf(this.dictType, value)
          if (label === undefined) {
            return this.placeholderOf(value)
          }
          return { value, label, code: '', sort: 0, status: 'enabled' } satisfies DictItem
        }),
      )
      return
    }
    const loader = this.source?.getType
    if (loader === undefined || this.source === undefined) {
      return
    }
    const token = (this.#resolveSeq += 1)
    this.markLoaded()
    this.loadingItems = true
    this.emitUpdate()
    try {
      const raw = await loader.call(this.source, {
        dictType: this.dictType,
        values: missing,
        limit: DICT_PROBE_LIMIT,
      })
      if (token !== this.#resolveSeq) {
        return
      }
      const result = normalizeDictTypeResult(raw)
      this.loadingItems = false
      this.#applyItems(result.items ?? [])
      this.emitUpdate()
    } catch (error) {
      if (token !== this.#resolveSeq) {
        return
      }
      this.loadingItems = false
      this.#applyError(error)
      this.emitUpdate()
    }
  }

  /**
   * 按值取条目（未解析返回 `undefined`）。
   *
   * @param value 条目值。
   * @returns 条目；未命中 `undefined`。
   */
  itemOf(value: string): DictItem | undefined {
    return findDictItem(this.items, value)
  }

  /**
   * 按值取展示文案（未解析回退值）。
   *
   * @param value 条目值。
   * @returns 展示文案。
   */
  labelOf(value: string): string {
    return this.itemOf(value)?.label ?? value
  }

  /** 选中回显文本（「、」连接；空值「—」）。 */
  selectionText(): string {
    const items = this.selectedItems
    return items.length === 0 ? DICT_EMPTY_VALUE : items.map((item) => item.label).join(DICT_JOIN)
  }

  /** 多选上限提示文案（0 不限返回空串）。 */
  limitText(): string {
    return this.limit > 0 ? `${DICT_LIMIT_TEXT_PREFIX} ${this.limit} 项` : ''
  }

  /**
   * 失效缓存（类型缓存 + 本地二次缓存）。
   */
  invalidate(): void {
    this.store?.invalidate(this.dictType)
    this.items.splice(0, this.items.length)
    this.options.splice(0, this.options.length)
    this.emitUpdate()
  }

  /** 从缓存层同步候选与回显（缓存更新后调用）。 */
  syncStore(): void {
    if (this.store === undefined || this.dictType === '') {
      return
    }
    if (this.store.isLoaded(this.dictType)) {
      this.#applyCandidates(filterDictItems(this.store.itemsOf(this.dictType), this.keyword))
    }
  }

  /**
   * 按值回显文案（数组 → 「、」连接；未解析回退值）。
   *
   * @param value 值（单值 / 数组）。
   */
  override getLabel(value: string | string[]): string | undefined {
    const values = normalizeDictValues(value, true)
    if (values.length === 0) {
      return undefined
    }
    if (Array.isArray(value)) {
      return values.map((entry) => this.labelOf(entry)).join(DICT_JOIN)
    }
    return this.labelOf(values[0] as string)
  }

  /**
   * 未解析项的展示占位（label 留空 → 展示回退值）。
   *
   * @param value 条目值。
   */
  private placeholderOf(value: string): DictItem {
    return { value, label: value, code: '', sort: 0, status: 'enabled' }
  }

  /**
   * 替换候选（已选项常驻；同步 `options` 与数据版本）。
   *
   * @param candidates 候选列表。
   */
  #applyCandidates(candidates: readonly DictItem[]): void {
    const keep = this.selectedItems.filter((item) => findDictItem(candidates, item.value) === undefined)
    this.#replaceItems(mergeDictItems(keep, candidates))
  }

  /**
   * 替换条目池（候选刷新；同步 `options` 与数据版本）。
   *
   * @param next 新条目列表。
   */
  #replaceItems(next: readonly DictItem[]): void {
    this.items.splice(0, this.items.length, ...next)
    this.options.splice(
      0,
      this.options.length,
      ...next.map((item) => ({ value: item.value, label: item.label })),
    )
    this.dataVersion += 1
    this.emitUpdate()
  }

  /**
   * 顶层过滤（级联场景回到顶层条目；非级联条目无 `parentId` 原样保留）。
   *
   * @param items 条目列表。
   * @returns 顶层条目。
   */
  #filterTopLevel(items: readonly DictItem[]): DictItem[] {
    const filtered = filterDictItems(items, this.keyword)
    return filtered.filter((item) => item.parentId === undefined)
  }

  /**
   * 并入条目池（同步 `options` 与数据版本）。
   *
   * @param incoming 增量列表。
   */
  #applyItems(incoming: readonly DictItem[]): void {
    const next = mergeDictItems(this.items, incoming)
    this.items.splice(0, this.items.length, ...next)
    this.options.splice(
      0,
      this.options.length,
      ...next.map((item) => ({ value: item.value, label: item.label })),
    )
    this.dataVersion += 1
    this.emitUpdate()
  }

  /**
   * 应用错误（错误码文案优先，回落加载失败文案）。
   *
   * @param error 原始错误。
   */
  #applyError(error: unknown): void {
    const code = readErrorCode(error)
    this.errorCode = code
    this.errorMessage = isDictErrorCode(code) ? resolveDictErrorText(code) : resolveDictErrorText(undefined)
    this.reportError(error, { scope: 'BaseDictSelect.load' })
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
