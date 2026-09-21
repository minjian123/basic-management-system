/** 字典选择族投影：把核心选择族组件基类 `BaseDictSelect` 与缓存能力 `BaseDictStore` 投影为组合式（缓存 / 批量合并 / 版本比对 / 回显 / 级联父值）。 */

import {
  BaseDictSelect,
  BaseDictStore,
  bindDictStoreSource,
  normalizeDictValues,
  type DictItem,
  type DictSourceAdapter,
  type DictStorageChannel,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

import { localStorageDictChannel } from '../utils/dictStorage'

/** 具体字典选择族（可实例化）。 */
class DictSelectState extends BaseDictSelect {}

/** 具体字典缓存（可实例化）。 */
class DictStoreState extends BaseDictStore {}

/** 字段值类型（单值 / 多选数组）。 */
export type DictSelectValue = string | number | (string | number)[]

/** `useBaseDictSelect` 选项。 */
export interface UseBaseDictSelectOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 字典类型码。 */
  dictType?: string
  /** 是否多选。 */
  multiple?: boolean
  /** 多选上限（0 不限）。 */
  limit?: number
  /** 初始值。 */
  value?: DictSelectValue
  /** 初始关键词。 */
  keyword?: string
  /** 级联父值（空串 = 顶层）。 */
  parentId?: string
  /** 语言。 */
  locale?: string
  /** 字典数据源（未注入即占位零请求）。 */
  source?: DictSourceAdapter
  /** 缓存能力（缺省内建实例，跨件共享请外部传入）。 */
  store?: BaseDictStore
  /** 本地二次缓存通道（缺省内建 localStorage 通道）。 */
  storage?: DictStorageChannel | undefined
  /** 件级禁用。 */
  disabled?: boolean
}

/** `useBaseDictSelect` 返回面（与核心方法一一对应的响应式面）。 */
export interface UseBaseDictSelectResult {
  /** 选择族实例。 */
  select: BaseDictSelect
  /** 缓存能力实例。 */
  store: BaseDictStore
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 生效禁用（件级禁用 ∨ 占位，响应式）。 */
  disabled: ComputedRef<boolean>
  /** 请求计数（占位态保持 0）。 */
  requestCount: Ref<number>
  /** 受控值（响应式）。 */
  value: Ref<string | string[] | undefined>
  /** 候选与回显条目（响应式）。 */
  items: Ref<DictItem[]>
  /** 选中值（响应式）。 */
  selectedValues: Ref<string[]>
  /** 选中条目（响应式）。 */
  selectedItems: Ref<DictItem[]>
  /** 关键词（响应式）。 */
  keyword: Ref<string>
  /** 级联父值（响应式）。 */
  parentId: Ref<string>
  /** 是否超大字典（响应式）。 */
  isLarge: Ref<boolean>
  /** 加载态（响应式）。 */
  loading: Ref<boolean>
  /** 是否错误态（响应式）。 */
  error: ComputedRef<boolean>
  /** 错误码（响应式）。 */
  errorCode: Ref<number | undefined>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 错误文案（响应式，同 `errorMessage`）。 */
  errorText: ComputedRef<string>
  /** 是否空态（响应式）。 */
  empty: ComputedRef<boolean>
  /** 多选超限标记（响应式）。 */
  limitExceeded: Ref<boolean>
  /** 多选上限提示文案（响应式）。 */
  limitText: ComputedRef<string>
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: DictSourceAdapter | undefined): void
  /** 切换字典类型。 */
  setDictType(dictType: string): void
  /** 设置关键词。 */
  setKeyword(keyword: string): void
  /** 设置级联父值。 */
  setParent(parentId: string): void
  /** 设置多选。 */
  setMultiple(value: boolean): void
  /** 设置上限。 */
  setLimit(limit: number): void
  /** 同步多选超限标记。 */
  setLimitExceeded(value: boolean): void
  /** 设置值（归一）。 */
  setValue(value: DictSelectValue | undefined): void
  /** 同步受控值并触发批量回显（件层 `modelValue` 监听用）。 */
  syncValue(value: DictSelectValue | undefined): void
  /** 选中 / 取消选中。 */
  toggle(value: string): void
  /** 移除选中项。 */
  remove(value: string): void
  /** 清空选中。 */
  clearSelection(): void
  /** 加载候选。 */
  load(): Promise<void>
  /** 远程搜索。 */
  searchRemote(keyword: string): Promise<DictItem[]>
  /** 批量回显。 */
  resolve(extra?: readonly string[]): Promise<void>
  /** 失效缓存。 */
  invalidate(): void
  /** 按值取展示文案。 */
  labelOf(value: string): string
  /** 选中回显文本。 */
  selectionText(): string
  /** 按值回显文案（数组「、」连接）。 */
  getLabel(value: string | string[]): string | undefined
  /** 订阅值变更。 */
  onValueChange(listener: (value: string | string[] | undefined) => void): () => void
}

/**
 * 使用字典选择投影。
 *
 * @param options 选项。
 * @returns 选择族实例与响应式面。
 */
export function useBaseDictSelect(options: UseBaseDictSelectOptions = {}): UseBaseDictSelectResult {
  const select = new DictSelectState()
  const store = options.store ?? new DictStoreState()
  const localDisabled = ref(options.disabled ?? false)

  // 显式传入 `storage`（含 `undefined`）以调用方为准；未传则用内建 localStorage 通道
  store.setStorage('storage' in options ? options.storage : localStorageDictChannel)
  select.setStore(store)
  if (options.locale !== undefined) {
    store.setLocale(options.locale)
  }
  if (options.ready !== undefined) {
    select.setReady(options.ready)
    store.setReady(options.ready)
  }
  if (options.dictType !== undefined) {
    select.setDictType(options.dictType)
  }
  if (options.multiple !== undefined) {
    select.setMultiple(options.multiple)
  }
  if (options.limit !== undefined) {
    select.setLimit(options.limit)
  }
  if (options.keyword !== undefined) {
    select.setKeyword(options.keyword)
  }
  if (options.parentId !== undefined) {
    select.setParent(options.parentId)
  }
  if (options.source !== undefined) {
    select.setSource(options.source)
    bindDictStoreSource(store, options.source)
  }
  if (options.value !== undefined) {
    select.setValue(toBaseValue(options.value, select.multiple))
  }

  const ready = ref(select.ready)
  const degraded = ref(select.degraded)
  const requestCount = ref(select.requestCount)
  const value = ref(select.value)
  const items = ref<DictItem[]>([...select.items])
  const selectedValues = ref<string[]>(select.selectedValues)
  const selectedItems = ref<DictItem[]>(select.selectedItems)
  const keyword = ref(select.keyword)
  const parentId = ref(select.parentId)
  const loading = ref(select.loadingItems)
  const errorCode = ref(select.errorCode)
  const errorMessage = ref(select.errorMessage)
  const limitExceeded = ref(select.limitExceeded)
  const isLarge = ref(select.isLarge)

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    ready.value = select.ready
    degraded.value = select.degraded
    requestCount.value = select.requestCount
    value.value = select.value
    items.value = [...select.items]
    selectedValues.value = select.selectedValues
    selectedItems.value = select.selectedItems
    keyword.value = select.keyword
    parentId.value = select.parentId
    loading.value = select.loadingItems
    errorCode.value = select.errorCode
    errorMessage.value = select.errorMessage
    limitExceeded.value = select.limitExceeded
    isLarge.value = select.isLarge
  }

  const off = select.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  const offValue = select.onChange(() => sync())
  const offStore = store.onLifecycle((event) => {
    if (event === 'update') {
      select.syncStore()
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    offValue()
    offStore()
    select.dispose()
    store.dispose()
  })

  const disabled = computed(() => localDisabled.value || !ready.value)
  const error = computed(() => errorCode.value !== undefined)
  const errorText = computed(() => errorMessage.value)
  const empty = computed(() => !loading.value && errorCode.value === undefined && items.value.length === 0)
  const limitText = computed(() => select.limitText())

  const api: UseBaseDictSelectResult = {
    select,
    store,
    ready,
    degraded,
    disabled,
    requestCount,
    value,
    items,
    selectedValues,
    selectedItems,
    keyword,
    parentId,
    isLarge,
    loading,
    error,
    errorCode,
    errorMessage,
    errorText,
    empty,
    limitExceeded,
    limitText,
    setReady: (next) => {
      select.setReady(next)
      store.setReady(next)
    },
    setSource: (next) => {
      select.setSource(next)
      bindDictStoreSource(store, next)
    },
    setDictType: (next) => select.setDictType(next),
    setKeyword: (next) => select.setKeyword(next),
    setParent: (next) => select.setParent(next),
    setMultiple: (next) => select.setMultiple(next),
    setLimit: (next) => select.setLimit(next),
    setLimitExceeded: (next) => select.setLimitExceeded(next),
    setValue: (next) => select.setValue(toBaseValue(next, select.multiple)),
    syncValue: (next) => {
      select.setValue(toBaseValue(next, select.multiple))
      sync()
      if (select.selectedValues.length > 0) {
        void select.resolve()
      }
    },
    toggle: (next) => select.toggle(next),
    remove: (next) => select.remove(next),
    clearSelection: () => select.clearSelection(),
    load: () => select.load(),
    searchRemote: (next) => select.searchRemote(next),
    resolve: (extra) => select.resolve(extra),
    invalidate: () => select.invalidate(),
    labelOf: (next) => select.labelOf(next),
    selectionText: () => select.selectionText(),
    getLabel: (next) => select.getLabel(next),
    onValueChange: (listener) => select.onChange(listener),
  }
  return api
}

/**
 * 字段值归一为核心值（保留入参形状：数组 → 数组，单值 → 单值；空值 `undefined`）。
 *
 * @param value 字段值。
 * @param multiple 是否多选（多选时空数组归一为 `undefined`）。
 * @returns 核心值。
 */
function toBaseValue(value: DictSelectValue | undefined, multiple: boolean): string | string[] | undefined {
  const values = normalizeDictValues(value, multiple)
  if (values.length === 0) {
    return undefined
  }
  return Array.isArray(value) ? values : values[0]
}
