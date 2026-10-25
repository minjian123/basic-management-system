/** 组织选择投影：把核心组织选择族组件基类 `BaseOrgSelect` 投影为组合式（远程搜索 / 批量回显 / 缓存 / 多选与上限 / 部门树）。 */

import {
  BaseOrgSelect,
  BaseUserDisplay,
  ORG_EMPTY_VALUE,
  normalizeOrgIds,
  orgLimitText,
  orgSelectionText,
  type OrgDeptNode,
  type OrgKind,
  type OrgOptionItem,
  type OrgSourceAdapter,
  type OrgStatus,
  type OrgTagSummary,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体组织选择族（可实例化）。 */
class OrgSelectState extends BaseOrgSelect {}

/** 具体用户展示（内建花名册通道）。 */
class UserDisplayState extends BaseUserDisplay {}

/** 字段值类型（单值 / 多选数组）。 */
export type OrgSelectValue = string | number | (string | number)[]

/** `useBaseOrgSelect` 选项。 */
export interface UseBaseOrgSelectOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 对象类型（缺省 user）。 */
  kind?: OrgKind
  /** 是否多选。 */
  multiple?: boolean
  /** 多选上限（0 不限）。 */
  limit?: number
  /** 初始值。 */
  value?: OrgSelectValue
  /** 初始关键词。 */
  keyword?: string
  /** 部门过滤。 */
  deptId?: string
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 状态过滤。 */
  status?: OrgStatus | ''
  /** 组织数据源（未注入即占位零请求）。 */
  source?: OrgSourceAdapter
  /** 用户展示能力（缺省内建花名册实例）。 */
  userDisplay?: BaseUserDisplay
  /** 件级禁用。 */
  disabled?: boolean
}

/** `useBaseOrgSelect` 返回面（与核心方法一一对应的响应式面）。 */
export interface UseBaseOrgSelectResult {
  /** 组织选择族实例。 */
  select: BaseOrgSelect
  /** 内建用户展示花名册实例。 */
  userDisplay: BaseUserDisplay
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
  /** 候选与已选选项（响应式）。 */
  items: Ref<OrgOptionItem[]>
  /** 部门树节点（响应式）。 */
  deptNodes: Ref<OrgDeptNode[]>
  /** 关键词（响应式）。 */
  keyword: Ref<string>
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
  /** 多选上限（响应式）。 */
  limit: Ref<number>
  /** 候选页码（响应式）。 */
  page: Ref<number>
  /** 候选总数（响应式）。 */
  total: Ref<number>
  /** 对象类型（响应式）。 */
  kind: Ref<OrgKind>
  /** 是否多选（响应式）。 */
  multiple: Ref<boolean>
  /** 状态过滤（响应式）。 */
  status: Ref<OrgStatus | ''>
  /** 部门过滤（响应式）。 */
  deptId: Ref<string>
  /** 部门过滤是否含下级（响应式）。 */
  includeChildren: Ref<boolean>
  /** 选中标识（响应式）。 */
  selectedIds: Ref<string[]>
  /** 选中项（响应式）。 */
  selectedItems: Ref<OrgOptionItem[]>
  /** 选中回显文本（响应式）。 */
  selectionText: ComputedRef<string>
  /** 多选上限提示文案（响应式）。 */
  limitText: ComputedRef<string>
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: OrgSourceAdapter | undefined): void
  /** 注入 / 移除用户展示能力。 */
  setUserDisplay(display: BaseUserDisplay | undefined): void
  /** 切换对象类型。 */
  setKind(kind: OrgKind): void
  /** 设置关键词。 */
  setKeyword(keyword: string): void
  /** 设置部门过滤。 */
  setDeptFilter(deptId: string, includeChildren?: boolean): void
  /** 设置状态过滤。 */
  setStatus(status: OrgStatus | ''): void
  /** 设置多选。 */
  setMultiple(value: boolean): void
  /** 设置多选上限。 */
  setLimit(limit: number): void
  /** 设置候选页码（夹取）。 */
  setPage(page: number): void
  /** 同步多选超限标记。 */
  setLimitExceeded(value: boolean): void
  /** 设置值（归一）。 */
  setValue(value: OrgSelectValue | undefined): void
  /** 同步受控值并触发批量回显（件层 `modelValue` 监听用）。 */
  syncValue(value: OrgSelectValue | undefined): void
  /** 选中 / 取消选中。 */
  toggle(id: string): void
  /** 移除选中项。 */
  remove(id: string): void
  /** 清空选中。 */
  clearSelection(): void
  /** 加载候选。 */
  load(): Promise<void>
  /** 批量回显。 */
  resolve(ids?: readonly string[]): Promise<void>
  /** 加载部门树。 */
  loadDeptTree(): Promise<void>
  /** 失效缓存。 */
  invalidate(kind?: OrgKind): void
  /** 按标识取展示文案。 */
  labelOf(id: string): string
  /** 选中标签摘要。 */
  tagSummary(maxVisible?: number): OrgTagSummary
  /** 订阅值变更。 */
  onValueChange(listener: (value: string | string[] | undefined) => void): () => void
}

/**
 * 使用组织选择投影。
 *
 * @param options 选项。
 * @returns 组织选择族实例与响应式面。
 */
export function useBaseOrgSelect(options: UseBaseOrgSelectOptions = {}): UseBaseOrgSelectResult {
  const select = new OrgSelectState()
  const userDisplay = options.userDisplay ?? new UserDisplayState()
  const localDisabled = ref(options.disabled ?? false)

  select.setUserDisplay(userDisplay)
  if (options.ready !== undefined) {
    select.setReady(options.ready)
  }
  if (options.kind !== undefined) {
    select.setKind(options.kind)
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
  if (options.deptId !== undefined || options.includeChildren !== undefined) {
    select.setDeptFilter(options.deptId ?? '', options.includeChildren ?? false)
  }
  if (options.status !== undefined) {
    select.setStatus(options.status)
  }
  if (options.source !== undefined) {
    select.setSource(options.source)
  }
  if (options.value !== undefined) {
    select.setValue(toBaseValue(options.value, select.multiple))
  }

  const ready = ref(select.ready)
  const degraded = ref(select.degraded)
  const requestCount = ref(select.requestCount)
  const value = ref(select.value)
  const items = ref<OrgOptionItem[]>([...select.items])
  const deptNodes = ref<OrgDeptNode[]>([...select.deptNodes])
  const keyword = ref(select.keyword)
  const loading = ref(select.loading)
  const errorCode = ref(select.errorCode)
  const errorMessage = ref(select.errorMessage)
  const limitExceeded = ref(select.limitExceeded)
  const limit = ref(select.limit)
  const page = ref(select.page)
  const total = ref(select.total)
  const kind = ref<OrgKind>(select.kind)
  const multiple = ref(select.multiple)
  const status = ref<OrgStatus | ''>(select.status)
  const deptId = ref(select.deptId)
  const includeChildren = ref(select.includeChildren)
  const selectedIds = ref<string[]>(select.selectedIds)
  const selectedItems = ref<OrgOptionItem[]>(select.selectedItems)

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    ready.value = select.ready
    degraded.value = select.degraded
    requestCount.value = select.requestCount
    value.value = select.value
    items.value = [...select.items]
    deptNodes.value = [...select.deptNodes]
    keyword.value = select.keyword
    loading.value = select.loading
    errorCode.value = select.errorCode
    errorMessage.value = select.errorMessage
    limitExceeded.value = select.limitExceeded
    limit.value = select.limit
    page.value = select.page
    total.value = select.total
    kind.value = select.kind
    multiple.value = select.multiple
    status.value = select.status
    deptId.value = select.deptId
    includeChildren.value = select.includeChildren
    selectedIds.value = select.selectedIds
    selectedItems.value = select.selectedItems
  }

  const off = select.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  const offValue = select.onChange(() => sync())
  onScopeDispose(() => {
    off()
    offValue()
    select.dispose()
  })

  const disabled = computed(() => localDisabled.value || !ready.value)
  const error = computed(() => errorCode.value !== undefined)
  const errorText = computed(() => errorMessage.value)
  const empty = computed(() => !loading.value && errorCode.value === undefined && items.value.length === 0)
  const selectionText = computed(() =>
    selectedItems.value.length === 0 ? ORG_EMPTY_VALUE : orgSelectionText(selectedItems.value),
  )
  const limitText = computed(() => orgLimitText(kind.value, limit.value))

  const api: UseBaseOrgSelectResult = {
    select,
    userDisplay,
    ready,
    degraded,
    disabled,
    requestCount,
    value,
    items,
    deptNodes,
    keyword,
    loading,
    error,
    errorCode,
    errorMessage,
    errorText,
    empty,
    limitExceeded,
    limit,
    page,
    total,
    kind,
    multiple,
    status,
    deptId,
    includeChildren,
    selectedIds,
    selectedItems,
    selectionText,
    limitText,
    setReady: (next) => select.setReady(next),
    setSource: (next) => select.setSource(next),
    setUserDisplay: (next) => select.setUserDisplay(next),
    setKind: (next) => select.setKind(next),
    setKeyword: (next) => select.setKeyword(next),
    setDeptFilter: (next, children) => select.setDeptFilter(next, children),
    setStatus: (next) => select.setStatus(next),
    setMultiple: (next) => {
      select.setMultiple(next)
      sync()
    },
    setLimit: (next) => select.setLimit(next),
    setPage: (next) => select.setPage(next),
    setLimitExceeded: (value) => select.setLimitExceeded(value),
    setValue: (next) => select.setValue(toBaseValue(next, select.multiple)),
    syncValue: (next) => {
      select.setValue(toBaseValue(next, select.multiple))
      sync()
      if (select.selectedIds.length > 0) {
        void select.resolve()
      }
    },
    toggle: (id) => select.toggle(id),
    remove: (id) => select.remove(id),
    clearSelection: () => select.clearSelection(),
    load: () => select.load(),
    resolve: (ids) => select.resolve(ids),
    loadDeptTree: () => select.loadDeptTree(),
    invalidate: (target) => select.invalidate(target),
    labelOf: (id) => select.labelOf(id),
    tagSummary: (maxVisible) => select.tagSummary(maxVisible),
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
function toBaseValue(value: OrgSelectValue | undefined, multiple: boolean): string | string[] | undefined {
  const ids = normalizeOrgIds(value, multiple)
  if (ids.length === 0) {
    return undefined
  }
  return Array.isArray(value) ? ids : ids[0]
}
