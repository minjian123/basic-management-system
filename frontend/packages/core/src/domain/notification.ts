/**
 * 领域纯函数：通知与消息（消息归一 / 角标 / 最近 N / 筛选 / 去重合并 / 乐观与回滚 / 轮询判定）。
 *
 * 不触 DOM、不请求、不依赖渲染框架与第三方库；同输入同输出。
 * 消息字段与后端 `sys_notification` 对齐（`read` 兼容 `is_read`）。
 */

import type { StatusSemantic } from './status'

/** 未读角标显示上限（超过显示 `99+`）。 */
export const NOTIFICATION_BADGE_MAX = 99

/** 铃铛下拉最近通知条数（缺省）。 */
export const NOTIFICATION_RECENT_LIMIT = 5

/** 未注入实时适配器时的轮询间隔（毫秒）。 */
export const NOTIFICATION_POLL_INTERVAL = 30_000

/** 列表页长缺省。 */
export const NOTIFICATION_PAGE_SIZE_DEFAULT = 20

/** 列表页长上限。 */
export const NOTIFICATION_PAGE_SIZE_MAX = 200

/** 批量已读 id 列表上限（与后端 70003 同源）。 */
export const NOTIFICATION_BATCH_MAX = 500

/** 消息类型。 */
export type NotificationMessageType = 'notice' | 'todo' | 'system'

/** 消息类型集合（与后端 `sys_notification.type` 同源）。 */
export const NOTIFICATION_TYPES: readonly NotificationMessageType[] = ['notice', 'todo', 'system']

/** 已读筛选档。 */
export type NotificationReadFilter = 'all' | 'unread' | 'read'

/** 已读筛选集合。 */
export const NOTIFICATION_READ_FILTERS: readonly NotificationReadFilter[] = ['all', 'unread', 'read']

/** 实时通道状态。 */
export type NotificationConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'offline'

/** 通知消息（归一形态）。 */
export interface NotificationMessage {
  /** 主键。 */
  id: string
  /** 标题。 */
  title: string
  /** 内容。 */
  content?: string
  /** 类型。 */
  type?: NotificationMessageType
  /** 是否已读。 */
  read?: boolean
  /** 创建时间（ISO 字符串）。 */
  createdAt?: string
  /** 业务来源类型（如 `wf_task`）。 */
  bizType?: string
  /** 业务来源单据 id。 */
  bizId?: string
}

/** 列表查询条件。 */
export interface NotificationQuery {
  /** 类型筛选（`all` 不过滤）。 */
  type?: NotificationMessageType | 'all'
  /** 已读筛选（`all` 不过滤）。 */
  read?: NotificationReadFilter
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  pageSize?: number
}

/** 列表结果（含未读数校准值）。 */
export interface NotificationPage {
  /** 消息清单。 */
  items: NotificationMessage[]
  /** 总数。 */
  total: number
  /** 未读数（服务端校准值；缺省不产出）。 */
  unreadCount?: number
}

/** 实时增量载荷（`notification.new` / `approval.todo`）。 */
export interface NotificationRealtimePayload {
  /** 主键（缺省按 `realtime:{createdAt}:{title}` 派生）。 */
  id?: string
  /** 标题。 */
  title: string
  /** 类型。 */
  type?: NotificationMessageType
  /** 业务来源类型。 */
  bizType?: string
  /** 业务来源单据 id。 */
  bizId?: string
  /** 创建时间。 */
  createdAt?: string
}

/** 乐观更新前的状态快照（回滚用）。 */
export interface NotificationSnapshot {
  /** 消息清单。 */
  items: NotificationMessage[]
  /** 未读数。 */
  unreadCount: number
  /** 总数。 */
  total: number
}

/**
 * 归一未读数（非有限值 / 负值回落 `0`）。
 *
 * @param value 原始未读数。
 * @returns 非负整数。
 */
function normalizeCount(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) {
    return 0
  }
  return Math.floor(numeric)
}

/**
 * 归一布尔（兼容 `true` / `1` / `'1'`）。
 *
 * @param value 原始值。
 * @returns 布尔值（无法识别返回 `undefined`）。
 */
function normalizeBool(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') {
    return value
  }
  if (value === 1 || value === '1' || value === 'true') {
    return true
  }
  if (value === 0 || value === '0' || value === 'false') {
    return false
  }
  return undefined
}

/**
 * 归一字符串（去首尾空格，空串回落 `undefined`）。
 *
 * @param value 原始值。
 * @returns 字符串或 `undefined`。
 */
function normalizeText(value: unknown): string | undefined {
  if (typeof value === 'string' && value.trim() !== '') {
    return value.trim()
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  return undefined
}

/**
 * 归一消息类型（非白名单回落 `notice`）。
 *
 * @param value 原始类型。
 * @returns 消息类型。
 */
function normalizeType(value: unknown): NotificationMessageType {
  const text = typeof value === 'string' ? value.trim() : ''
  return (NOTIFICATION_TYPES as readonly string[]).includes(text)
    ? (text as NotificationMessageType)
    : 'notice'
}

/**
 * 派生实时增量的稳定键。
 *
 * @param payload 实时载荷。
 * @returns 消息键。
 */
function realtimeKeyOf(payload: NotificationRealtimePayload): string {
  const id = normalizeText(payload.id)
  if (id !== undefined) {
    return id
  }
  return `realtime:${normalizeText(payload.createdAt) ?? ''}:${normalizeText(payload.title) ?? ''}`
}

/**
 * 归一单条消息（缺 `id` / `title` 视为脏项）。
 *
 * @param value 原始消息。
 * @returns 归一消息或 `undefined`。
 */
export function normalizeNotificationMessage(value: unknown): NotificationMessage | undefined {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  const raw = value as Record<string, unknown>
  const id = normalizeText(raw.id)
  const title = normalizeText(raw.title)
  if (id === undefined || title === undefined) {
    return undefined
  }
  const message: NotificationMessage = { id, title }
  const content = normalizeText(raw.content)
  if (content !== undefined) {
    message.content = content
  }
  if (raw.type !== undefined) {
    message.type = normalizeType(raw.type)
  }
  const read = normalizeBool(raw.read ?? raw.is_read)
  message.read = read ?? false
  const createdAt = normalizeText(raw.createdAt ?? raw.created_at)
  if (createdAt !== undefined) {
    message.createdAt = createdAt
  }
  const bizType = normalizeText(raw.bizType ?? raw.biz_type)
  if (bizType !== undefined) {
    message.bizType = bizType
  }
  const bizId = normalizeText(raw.bizId ?? raw.biz_id)
  if (bizId !== undefined) {
    message.bizId = bizId
  }
  return message
}

/**
 * 归一消息数组（脏项剔除）。
 *
 * @param value 原始数组。
 * @returns 归一消息数组。
 */
export function normalizeNotificationMessages(value: unknown): NotificationMessage[] {
  if (!Array.isArray(value)) {
    return []
  }
  const out: NotificationMessage[] = []
  for (const entry of value) {
    const message = normalizeNotificationMessage(entry)
    if (message !== undefined) {
      out.push(message)
    }
  }
  return out
}

/**
 * 归一列表结果（非对象 / 脏项回落空页）。
 *
 * @param value 原始结果（可为数组或 `{ items, total, unreadCount }`）。
 * @returns 归一列表结果。
 */
export function normalizeNotificationPage(value: unknown): NotificationPage {
  if (Array.isArray(value)) {
    const items = normalizeNotificationMessages(value)
    return { items, total: items.length }
  }
  if (value === null || typeof value !== 'object') {
    return { items: [], total: 0 }
  }
  const raw = value as Record<string, unknown>
  const items = normalizeNotificationMessages(raw.items)
  const totalRaw = raw.total
  const total =
    typeof totalRaw === 'number' && Number.isFinite(totalRaw) && totalRaw >= 0 ? Math.floor(totalRaw) : items.length
  const page: NotificationPage = { items, total }
  if (raw.unreadCount !== undefined || raw.unread_count !== undefined) {
    page.unreadCount = parseUnreadCount(raw.unreadCount ?? raw.unread_count)
  }
  return page
}

/**
 * 判断单条消息是否未读。
 *
 * @param message 消息。
 * @returns 是否未读。
 */
export function isUnread(message: NotificationMessage): boolean {
  return message.read !== true
}

/**
 * 统计未读消息数。
 *
 * @param items 消息数组。
 * @returns 未读数。
 */
export function countUnread(items: readonly NotificationMessage[]): number {
  let count = 0
  for (const item of items) {
    if (isUnread(item)) {
      count += 1
    }
  }
  return count
}

/**
 * 夹取角标计数到 `0 ~ max`。
 *
 * @param count 原始计数。
 * @param max 上限（缺省 `NOTIFICATION_BADGE_MAX`）。
 * @returns 夹取后的整数。
 */
export function clampBadgeCount(count: unknown, max: number = NOTIFICATION_BADGE_MAX): number {
  const normalized = normalizeCount(count)
  const limit = Math.max(0, Math.floor(max))
  return Math.min(normalized, limit)
}

/**
 * 角标文案（`0` → 空串、`> max` → `${max}+`）。
 *
 * @param count 原始计数。
 * @param max 上限（缺省 `NOTIFICATION_BADGE_MAX`）。
 * @returns 角标文案。
 */
export function badgeTextOf(count: unknown, max: number = NOTIFICATION_BADGE_MAX): string {
  const normalized = normalizeCount(count)
  const limit = Math.max(0, Math.floor(max))
  if (normalized <= 0) {
    return ''
  }
  if (normalized > limit) {
    return `${limit}+`
  }
  return String(normalized)
}

/**
 * 是否显示角标（仅 `count > 0`）。
 *
 * @param count 原始计数。
 * @returns 是否显示。
 */
export function shouldShowBadge(count: unknown): boolean {
  return normalizeCount(count) > 0
}

/**
 * 解析未读数（非有限值 / 负值回落 `0`）。
 *
 * @param value 原始未读数。
 * @returns 非负整数。
 */
export function parseUnreadCount(value: unknown): number {
  return normalizeCount(value)
}

/**
 * 取最近 N 条（按创建时间降序，时间缺失视为最旧且稳定保序）。
 *
 * @param items 消息数组。
 * @param limit 条数（缺省 `NOTIFICATION_RECENT_LIMIT`）。
 * @returns 最近 N 条（新数组）。
 */
export function recentMessages(
  items: readonly NotificationMessage[],
  limit: number = NOTIFICATION_RECENT_LIMIT,
): NotificationMessage[] {
  const count = Math.max(0, Math.floor(limit))
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => {
      const left = a.item.createdAt ?? ''
      const right = b.item.createdAt ?? ''
      if (left === right) {
        return a.index - b.index
      }
      if (left === '') {
        return 1
      }
      if (right === '') {
        return -1
      }
      return left < right ? 1 : -1
    })
    .slice(0, count)
    .map((entry) => entry.item)
}

/**
 * 按类型 / 已读筛选消息。
 *
 * @param items 消息数组。
 * @param query 查询条件。
 * @returns 命中消息（新数组）。
 */
export function filterNotificationMessages(
  items: readonly NotificationMessage[],
  query: NotificationQuery,
): NotificationMessage[] {
  const type = query.type ?? 'all'
  const read = query.read ?? 'all'
  return items.filter((item) => {
    if (type !== 'all' && (item.type ?? 'notice') !== type) {
      return false
    }
    if (read === 'unread') {
      return isUnread(item)
    }
    if (read === 'read') {
      return !isUnread(item)
    }
    return true
  })
}

/**
 * 按 `id` 去重合并（命中更新并保原序，未命中新项置于最前）。
 *
 * @param existing 既有消息。
 * @param incoming 新增消息。
 * @returns 合并后的新数组。
 */
export function mergeMessages(
  existing: readonly NotificationMessage[],
  incoming: readonly NotificationMessage[],
): NotificationMessage[] {
  const result = existing.map((item) => ({ ...item }))
  const index = new Map<string, number>()
  result.forEach((item, position) => index.set(item.id, position))
  const fresh: NotificationMessage[] = []
  for (const item of incoming) {
    const position = index.get(item.id)
    if (position === undefined) {
      fresh.push({ ...item })
    } else {
      result[position] = { ...result[position], ...item }
    }
  }
  return [...fresh, ...result]
}

/**
 * 应用实时增量（去重 + 未读 +1；同键此前存在则仅更新）。
 *
 * @param snapshot 当前快照。
 * @param payload 实时载荷。
 * @returns 新快照。
 */
export function applyIncoming(
  snapshot: NotificationSnapshot,
  payload: NotificationRealtimePayload,
): NotificationSnapshot {
  const id = realtimeKeyOf(payload)
  const message: NotificationMessage = { id, title: payload.title, read: false }
  if (payload.type !== undefined) {
    message.type = normalizeType(payload.type)
  }
  if (payload.createdAt !== undefined) {
    message.createdAt = payload.createdAt
  }
  if (payload.bizType !== undefined) {
    message.bizType = payload.bizType
  }
  if (payload.bizId !== undefined) {
    message.bizId = payload.bizId
  }
  const exists = snapshot.items.some((item) => item.id === id)
  const items = exists ? mergeMessages(snapshot.items, [message]) : [message, ...snapshot.items]
  const unreadCount = exists ? snapshot.unreadCount : snapshot.unreadCount + 1
  const total = exists ? snapshot.total : snapshot.total + 1
  return { items, unreadCount, total }
}

/**
 * 乐观标记指定 id 已读。
 *
 * @param snapshot 当前快照。
 * @param ids 目标 id 集合。
 * @returns 新快照与变更计数。
 */
export function applyOptimisticRead(
  snapshot: NotificationSnapshot,
  ids: readonly string[],
): { snapshot: NotificationSnapshot; changed: number } {
  const targets = new Set(ids)
  let changed = 0
  const items = snapshot.items.map((item) => {
    if (targets.has(item.id) && isUnread(item)) {
      changed += 1
      return { ...item, read: true }
    }
    return { ...item }
  })
  return {
    snapshot: {
      items,
      unreadCount: Math.max(0, snapshot.unreadCount - changed),
      total: snapshot.total,
    },
    changed,
  }
}

/**
 * 乐观标记全部已读。
 *
 * @param snapshot 当前快照。
 * @returns 新快照与变更计数。
 */
export function applyOptimisticReadAll(snapshot: NotificationSnapshot): {
  snapshot: NotificationSnapshot
  changed: number
} {
  const changed = countUnread(snapshot.items)
  const items = snapshot.items.map((item) => (isUnread(item) ? { ...item, read: true } : { ...item }))
  return { snapshot: { items, unreadCount: 0, total: snapshot.total }, changed }
}

/**
 * 乐观删除指定消息。
 *
 * @param snapshot 当前快照。
 * @param id 目标 id。
 * @returns 新快照与变更计数。
 */
export function applyOptimisticRemove(
  snapshot: NotificationSnapshot,
  id: string,
): { snapshot: NotificationSnapshot; changed: number } {
  const target = snapshot.items.find((item) => item.id === id)
  if (target === undefined) {
    return { snapshot: restoreSnapshot(snapshot), changed: 0 }
  }
  const items = snapshot.items.filter((item) => item.id !== id).map((item) => ({ ...item }))
  const wasUnread = isUnread(target)
  return {
    snapshot: {
      items,
      unreadCount: wasUnread ? Math.max(0, snapshot.unreadCount - 1) : snapshot.unreadCount,
      total: Math.max(0, snapshot.total - 1),
    },
    changed: 1,
  }
}

/**
 * 复制快照（消息项与数组均新引用，防共享引用污染）。
 *
 * @param snapshot 快照。
 * @returns 新快照。
 */
export function restoreSnapshot(snapshot: NotificationSnapshot): NotificationSnapshot {
  return {
    items: snapshot.items.map((item) => ({ ...item })),
    unreadCount: snapshot.unreadCount,
    total: snapshot.total,
  }
}

/**
 * 消息类型 → 语义色（`notice` → `info`、`todo` → `warning`、`system` → `primary`）。
 *
 * @param type 消息类型。
 * @returns 语义色。
 */
export function resolveMessageSemantic(type: unknown): StatusSemantic {
  if (type === 'todo') {
    return 'warning'
  }
  if (type === 'system') {
    return 'primary'
  }
  return 'info'
}

/**
 * 消息类型中文标签。
 *
 * @param type 消息类型。
 * @returns 标签（未知类型回落空串）。
 */
export function messageTypeLabel(type: unknown): string {
  if (type === 'notice') {
    return '站内信'
  }
  if (type === 'todo') {
    return '待办提醒'
  }
  if (type === 'system') {
    return '系统提示'
  }
  return ''
}

/**
 * 解析跳转目标（`bizType` 与 `bizId` 均非空才成立）。
 *
 * @param message 消息。
 * @returns 跳转目标或 `undefined`。
 */
export function jumpTargetOf(message: NotificationMessage): { bizType: string; bizId: string } | undefined {
  const bizType = normalizeText(message.bizType)
  const bizId = normalizeText(message.bizId)
  if (bizType === undefined || bizId === undefined) {
    return undefined
  }
  return { bizType, bizId }
}

/**
 * 是否具备跳转目标。
 *
 * @param message 消息。
 * @returns 是否可跳转。
 */
export function hasJumpTarget(message: NotificationMessage): boolean {
  return jumpTargetOf(message) !== undefined
}

/**
 * 构造列表查询参数（与后端 `/notifications` 查询契约同源）。
 *
 * @param query 查询条件。
 * @returns 查询参数对象。
 */
export function buildNotificationParams(query: NotificationQuery): {
  type?: string
  is_read?: number
  page?: number
  size?: number
} {
  const params: { type?: string; is_read?: number; page?: number; size?: number } = {}
  if (query.type !== undefined && query.type !== 'all') {
    params.type = query.type
  }
  if (query.read === 'unread') {
    params.is_read = 0
  } else if (query.read === 'read') {
    params.is_read = 1
  }
  if (query.page !== undefined && Number.isFinite(query.page) && query.page >= 1) {
    params.page = Math.floor(query.page)
  }
  if (query.pageSize !== undefined && Number.isFinite(query.pageSize) && query.pageSize >= 1) {
    params.size = Math.floor(query.pageSize)
  }
  return params
}

/**
 * 是否需要轮询占位（就绪且未注入实时适配器）。
 *
 * @param ready 数据通路是否就绪。
 * @param hasRealtime 是否已注入实时适配器。
 * @returns 是否需要轮询。
 */
export function isPollingNeeded(ready: boolean, hasRealtime: boolean): boolean {
  return ready && !hasRealtime
}

/**
 * 是否应当触发一次轮询（页面可见且达间隔）。
 *
 * @param visible 页面是否可见。
 * @param lastMs 上次轮询时刻（毫秒）。
 * @param nowMs 当前时刻（毫秒）。
 * @param intervalMs 间隔（缺省 `NOTIFICATION_POLL_INTERVAL`）。
 * @returns 是否触发。
 */
export function shouldPoll(
  visible: boolean,
  lastMs: number,
  nowMs: number,
  intervalMs: number = NOTIFICATION_POLL_INTERVAL,
): boolean {
  return visible && nowMs - lastMs >= Math.max(0, intervalMs)
}

/**
 * 实时连接状态文案。
 *
 * @param state 连接状态。
 * @returns 文案。
 */
export function connectionLabel(state: NotificationConnectionState): string {
  if (state === 'connected') {
    return '实时已连接'
  }
  if (state === 'reconnecting') {
    return '实时重连中'
  }
  if (state === 'offline') {
    return '实时已断开'
  }
  return '实时未连接'
}
