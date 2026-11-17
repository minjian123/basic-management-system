/**
 * 审计差异取数组合式：把 `AuditQueryAdapter` 的字段级变更行分组为记录、映射为 `AuditDiff` 入参。
 *
 * `AuditDiff` 保持**纯 props**（不取数）；页面 / 弹层经本组合式取数与选中，再把结果传入组件。
 */

import { BaseDataState, groupAuditRows, normalizeAuditRows, parseAuditJson, type AuditRecordGroup, type AuditRow } from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

import type { AuditPageQuery, AuditQueryAdapter } from '../utils/auditQuery'

/** 审计取数状态机（加载 / 就绪 / 空 / 错误 + 竞态令牌）。 */
class AuditDataState extends BaseDataState {}

/** 记录行（与 `AuditDiff` 的 `AuditRecord` 结构一致）。 */
export interface AuditRecordView {
  /** 主键（事件键）。 */
  id: string
  /** 表名。 */
  tableName: string
  /** 记录 ID。 */
  recordId: string
  /** 变更字段数。 */
  fields?: number
  /** 操作人。 */
  operator?: string
  /** 变更时间。 */
  createdAt?: string
}

/** 字段级差异（与 `AuditDiff` 的 `AuditFieldDiff` 结构一致）。 */
export interface AuditFieldDiffView {
  /** 字段名。 */
  field: string
  /** 字段标签。 */
  label?: string
  /** 旧值。 */
  oldValue?: unknown
  /** 新值。 */
  newValue?: unknown
  /** 渲染类型。 */
  valueType?: string
}

/** 组合式选项。 */
export interface UseAuditDiffOptions {
  /** 数据通路是否就绪（缺省 `false`，未就绪零请求）。 */
  ready?: boolean
  /** 取数适配器（未注入即不请求）。 */
  query?: AuditQueryAdapter
}

/** 组合式返回面。 */
export interface UseAuditDiffResult {
  /** 记录行（按 `event_id` 分组）。 */
  records: Ref<AuditRecordView[]>
  /** 选中记录的事件键。 */
  selectedEventId: Ref<string>
  /** 选中记录的字段差异。 */
  diff: Ref<AuditFieldDiffView[]>
  /** 选中记录的前序哈希。 */
  prevHash: Ref<string>
  /** 选中记录的记录哈希。 */
  recordHash: Ref<string>
  /** 链校验结果（未校验 `undefined`）。 */
  chainVerified: Ref<boolean | undefined>
  /** 链校验说明（失败 / 断裂定位）。 */
  chainMessage: Ref<string>
  /** 当前页。 */
  page: Ref<number>
  /** 总条数（按字段行计，页面注明）。 */
  total: Ref<number>
  /** 加载中。 */
  loading: Ref<boolean>
  /** 错误文案。 */
  errorMessage: Ref<string>
  /** 是否有错误。 */
  error: ComputedRef<boolean>
  /** 加载指定筛选条件。 */
  load(filter: AuditPageQuery): Promise<void>
  /** 选中记录（本地分组映射，不额外请求）。 */
  select(eventId: string): void
  /** 链校验。 */
  verify(months?: string): Promise<void>
  /** 重置（清空记录与选中）。 */
  reset(): void
}

/**
 * 记录组 → `AuditDiff` 的记录行。
 *
 * @param group 记录组。
 * @returns 记录行。
 */
function toRecord(group: AuditRecordGroup): AuditRecordView {
  const record: AuditRecordView = {
    id: group.eventId,
    tableName: group.tableName,
    recordId: group.recordId ?? '',
    fields: group.rows.length,
  }
  if (group.operatorId !== undefined) {
    record.operator = group.operatorId
  }
  if (group.occurredAt !== undefined) {
    record.createdAt = group.occurredAt
  }
  return record
}

/**
 * 字段行 → 字段差异（旧 / 新值 JSON 解析）。
 *
 * @param row 字段行。
 * @returns 字段差异。
 */
function toFieldDiff(row: AuditRow): AuditFieldDiffView {
  const diff: AuditFieldDiffView = {
    field: row.field,
    oldValue: parseAuditJson(row.oldValue),
    newValue: parseAuditJson(row.newValue),
  }
  return diff
}

/**
 * 使用审计差异取数组合式。
 *
 * @param options 选项。
 * @returns 响应式面与命令。
 */
export function useAuditDiff(options: UseAuditDiffOptions = {}): UseAuditDiffResult {
  const ready = options.ready ?? false
  const records = ref<AuditRecordView[]>([])
  const selectedEventId = ref('')
  const diff = ref<AuditFieldDiffView[]>([])
  const prevHash = ref('')
  const recordHash = ref('')
  const chainVerified = ref<boolean | undefined>(undefined)
  const chainMessage = ref('')
  const page = ref(1)
  const total = ref(0)
  const loading = ref(false)
  const errorMessage = ref('')

  /** 已加载的分组（选中时复用，不重复请求）。 */
  let groups: AuditRecordGroup[] = []
  /** 取数状态机（竞态下旧请求不覆盖新结果）。 */
  const state = new AuditDataState()
  onScopeDispose(() => state.dispose())

  const error = computed(() => errorMessage.value !== '')

  /**
   * 加载列表。
   *
   * @param filter 筛选条件。
   */
  async function load(filter: AuditPageQuery): Promise<void> {
    if (!ready || options.query === undefined) {
      return
    }
    const token = state.begin()
    loading.value = true
    errorMessage.value = ''
    try {
      const raw = await options.query.page(filter)
      const rows = normalizeAuditRows(raw)
      const source = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
      const nextGroups = groupAuditRows(rows)
      const nextRecords = nextGroups.map(toRecord)
      if (!state.settle(token, nextRecords.length > 0 ? 'ready' : 'empty')) {
        return
      }
      groups = nextGroups
      records.value = nextRecords
      page.value = typeof source.page === 'number' ? source.page : 1
      total.value =
        typeof source.total === 'number' && Number.isFinite(source.total) ? Math.floor(source.total) : rows.length
      selectedEventId.value = ''
      diff.value = []
      prevHash.value = ''
      recordHash.value = ''
      loading.value = false
    } catch (cause) {
      if (!state.settle(token, 'error')) {
        return
      }
      errorMessage.value = cause instanceof Error && cause.message !== '' ? cause.message : '审计数据加载失败'
      loading.value = false
    }
  }

  /**
   * 选中记录（从已加载分组映射字段差异）。
   *
   * @param eventId 事件键。
   */
  function select(eventId: string): void {
    const group = groups.find((entry) => entry.eventId === eventId)
    if (group === undefined) {
      return
    }
    selectedEventId.value = eventId
    diff.value = group.rows.map(toFieldDiff)
    prevHash.value = group.prevHash
    recordHash.value = group.recordHash
  }

  /**
   * 链校验。
   *
   * @param months 月份（逗号分隔；空 = 台账全部）。
   */
  async function verify(months?: string): Promise<void> {
    if (!ready || options.query === undefined) {
      return
    }
    errorMessage.value = ''
    try {
      const raw = await options.query.verify(months)
      const source = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
      chainVerified.value = source.valid === true
      if (source.valid === true) {
        chainMessage.value = ''
        return
      }
      const month = typeof source.broken_month === 'string' ? source.broken_month : ''
      chainMessage.value = month === '' ? '审计链校验未通过' : `审计链在 ${month} 分片断裂`
    } catch (cause) {
      chainVerified.value = false
      chainMessage.value = cause instanceof Error && cause.message !== '' ? cause.message : '审计链校验失败'
    }
  }

  /** 重置。 */
  function reset(): void {
    groups = []
    records.value = []
    selectedEventId.value = ''
    diff.value = []
    prevHash.value = ''
    recordHash.value = ''
    page.value = 1
    total.value = 0
    errorMessage.value = ''
  }

  return {
    records,
    selectedEventId,
    diff,
    prevHash,
    recordHash,
    chainVerified,
    chainMessage,
    page,
    total,
    loading,
    errorMessage,
    error,
    load,
    select,
    verify,
    reset,
  }
}

