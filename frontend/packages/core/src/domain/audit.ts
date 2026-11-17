/**
 * 审计领域纯函数：字段级变更行归一 / 按事件分组 / 旧新值 JSON 解析。
 *
 * 后端 `GET /api/v1/audit/data-changes` 每行是**一个字段的变更**（`event_id` 同属一次业务动作），
 * 组件按「记录（事件）」渲染，故此处提供分组与值解析；不触 DOM、不请求。
 */

/** 字段级变更行（`DataChangeItem` 前端形态）。 */
export interface AuditRow {
  /** 审计主键。 */
  id: string
  /** 事件幂等键（同一次业务动作的多字段行共用）。 */
  eventId: string
  /** 被审计逻辑表名。 */
  tableName: string
  /** 被审计记录主键。 */
  recordId?: string
  /** 变更字段名。 */
  field: string
  /** 变更前值（JSON 文本；敏感列已脱敏为 `***`）。 */
  oldValue?: string
  /** 变更后值（JSON 文本）。 */
  newValue?: string
  /** 操作人主键。 */
  operatorId?: string
  /** 业务域。 */
  domainKey?: string
  /** 事件发生时间（ISO）。 */
  occurredAt?: string
  /** 前序哈希。 */
  prevHash?: string
  /** 本条记录哈希。 */
  recordHash?: string
  /** 写入时间（ISO）。 */
  createdAt?: string
}

/** 按事件聚合的变更记录。 */
export interface AuditRecordGroup {
  /** 事件幂等键（记录行的稳定标识）。 */
  eventId: string
  /** 被审计逻辑表名。 */
  tableName: string
  /** 被审计记录主键。 */
  recordId?: string
  /** 操作人主键。 */
  operatorId?: string
  /** 事件发生时间（ISO）。 */
  occurredAt?: string
  /** 组内首行的前序哈希。 */
  prevHash: string
  /** 组内末行的记录哈希。 */
  recordHash: string
  /** 字段级变更行（保持后端顺序）。 */
  rows: AuditRow[]
}

/**
 * 读字符串（非字符串 / 空串返回 `undefined`）。
 *
 * @param value 原始值。
 * @returns 字符串或 `undefined`。
 */
function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value !== '' ? value : undefined
}

/**
 * 读主键（数字转字符串，保精度；缺失返回 `undefined`）。
 *
 * @param value 原始值。
 * @returns 主键字符串或 `undefined`。
 */
function readId(value: unknown): string | undefined {
  if (typeof value === 'string' && value !== '') {
    return value
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return undefined
}

/**
 * 归一字段级变更行（兼容 snake_case；`id` / `event_id` / `table_name` / `field` 必需）。
 *
 * @param raw 原始数据。
 * @returns 变更行；不可用返回 `undefined`。
 */
export function normalizeAuditRow(raw: unknown): AuditRow | undefined {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined
  }
  const source = raw as Record<string, unknown>
  const id = readId(source.id)
  const eventId = readString(source.event_id) ?? readString(source.eventId)
  const tableName = readString(source.table_name) ?? readString(source.tableName)
  const field = readString(source.field)
  if (id === undefined || eventId === undefined || tableName === undefined || field === undefined) {
    return undefined
  }
  const row: AuditRow = { id, eventId, tableName, field }
  const recordId = readId(source.record_id ?? source.recordId)
  if (recordId !== undefined) {
    row.recordId = recordId
  }
  const oldValue = readString(source.old_value ?? source.oldValue)
  if (oldValue !== undefined) {
    row.oldValue = oldValue
  }
  const newValue = readString(source.new_value ?? source.newValue)
  if (newValue !== undefined) {
    row.newValue = newValue
  }
  const operatorId = readId(source.operator_id ?? source.operatorId)
  if (operatorId !== undefined) {
    row.operatorId = operatorId
  }
  const domainKey = readString(source.domain_key ?? source.domainKey)
  if (domainKey !== undefined) {
    row.domainKey = domainKey
  }
  const occurredAt = readString(source.occurred_at ?? source.occurredAt)
  if (occurredAt !== undefined) {
    row.occurredAt = occurredAt
  }
  const prevHash = readString(source.prev_hash ?? source.prevHash)
  if (prevHash !== undefined) {
    row.prevHash = prevHash
  }
  const recordHash = readString(source.record_hash ?? source.recordHash)
  if (recordHash !== undefined) {
    row.recordHash = recordHash
  }
  const createdAt = readString(source.created_at ?? source.createdAt)
  if (createdAt !== undefined) {
    row.createdAt = createdAt
  }
  return row
}

/**
 * 归一变更行列表（兼容数组 / `{ list }` / `{ items }` / `{ data }` 包装）。
 *
 * @param raw 原始数据。
 * @returns 变更行列表（脏项剔除）。
 */
export function normalizeAuditRows(raw: unknown): AuditRow[] {
  let list: unknown[] = []
  if (Array.isArray(raw)) {
    list = raw
  } else if (raw !== null && typeof raw === 'object') {
    const source = raw as Record<string, unknown>
    for (const key of ['list', 'items', 'data']) {
      const value = source[key]
      if (Array.isArray(value)) {
        list = value
        break
      }
    }
  }
  const rows: AuditRow[] = []
  for (const entry of list) {
    const row = normalizeAuditRow(entry)
    if (row !== undefined) {
      rows.push(row)
    }
  }
  return rows
}

/**
 * 按 `event_id` 分组为记录行（保持后端顺序；哈希取组内首尾）。
 *
 * @param rows 变更行列表。
 * @returns 记录组列表。
 */
export function groupAuditRows(rows: readonly AuditRow[]): AuditRecordGroup[] {
  const order: string[] = []
  const map = new Map<string, AuditRecordGroup>()
  for (const row of rows) {
    const existing = map.get(row.eventId)
    if (existing === undefined) {
      order.push(row.eventId)
      map.set(row.eventId, {
        eventId: row.eventId,
        tableName: row.tableName,
        ...(row.recordId === undefined ? {} : { recordId: row.recordId }),
        ...(row.operatorId === undefined ? {} : { operatorId: row.operatorId }),
        ...(row.occurredAt === undefined ? {} : { occurredAt: row.occurredAt }),
        prevHash: row.prevHash ?? '',
        recordHash: row.recordHash ?? '',
        rows: [row],
      })
      continue
    }
    existing.rows.push(row)
    if (row.recordHash !== undefined && row.recordHash !== '') {
      existing.recordHash = row.recordHash
    }
  }
  return order.map((eventId) => map.get(eventId) as AuditRecordGroup)
}

/**
 * 解析审计值（JSON 文本；解析失败保留原文；空值 `undefined`）。
 *
 * @param text 原始文本。
 * @returns 解析后的值或原文。
 */
export function parseAuditJson(text: string | undefined): unknown {
  if (text === undefined || text === '') {
    return undefined
  }
  try {
    return JSON.parse(text) as unknown
  } catch {
    return text
  }
}
