/**
 * 通知 HTTP 取数适配器：把后端 `/api/v1/notifications/*` 接到通知中心编排能力（`NotificationJobs`）。
 *
 * - 列表：`GET /notifications?page&size&type&is_read`（响应 `list` / `total` 由核心归一）；
 * - 未读：`GET /notifications/unread-count` → `{ count }`；
 * - 详情：`GET /notifications/{id}?mark_read=true`（查看即已读）；
 * - 批量已读：`POST /notifications/read`（体 `{ ids }`）；全部已读：`POST /notifications/read-all`；
 * - 删除：`DELETE /notifications/{id}`。
 *
 * 请求类型映射：前端 `todo` → 后端 `approval`，`system` → `system`，`notice` → `alert`（后端通知类）；
 * 响应侧类型别名反向归一见核心 `normalizeNotificationType`。
 */

import type { NotificationJobs, NotificationQuery } from '@bms/core'

/** 后端通知类型（列表筛选入参）。 */
const REQUEST_TYPE: Readonly<Record<string, string>> = {
  todo: 'approval',
  system: 'system',
  notice: 'alert',
}

/** 适配器选项。 */
export interface NotificationHttpOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/**
 * 解统一响应包装（`{ code, message, data }`；业务码非 0 / 200 抛错）。
 *
 * @param payload 原始响应体。
 * @returns 数据体。
 */
function unwrapResponse(payload: unknown): unknown {
  if (payload !== null && typeof payload === 'object' && !Array.isArray(payload)) {
    const record = payload as { code?: unknown; message?: unknown; data?: unknown }
    if (typeof record.code === 'number') {
      if (record.code !== 0 && record.code !== 200) {
        throw new Error(typeof record.message === 'string' && record.message !== '' ? record.message : '通知服务不可用')
      }
      return record.data
    }
  }
  return payload
}

/**
 * 读取未读数（兼容 `{ count }` / 裸数）。
 *
 * @param raw 原始数据。
 * @returns 未读数（非负整数）。
 */
function readCount(raw: unknown): number {
  const value = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>).count : raw
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? Math.floor(numeric) : 0
}

/**
 * 创建通知 HTTP 取数适配器。
 *
 * @param options 适配器选项。
 * @returns 通知处理函数集（未覆盖 `fetch` 能力时请求直接失败，由编排回错误态）。
 */
export function createHttpNotificationJobs(options: NotificationHttpOptions = {}): NotificationJobs {
  const endpoint = (options.endpoint ?? '/api/v1').replace(/\/+$/, '')

  /**
   * 发起请求并解包。
   *
   * @param method 方法。
   * @param path 路径（相对端点前缀）。
   * @param payload 查询参数（GET / DELETE）或请求体（POST）。
   * @returns 数据体。
   */
  async function request(
    method: 'GET' | 'POST' | 'DELETE',
    path: string,
    payload: Record<string, unknown> = {},
  ): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      throw new Error('通知服务不可用')
    }
    const headers = typeof options.headers === 'function' ? options.headers() : options.headers
    let url = `${endpoint}${path}`
    const init: RequestInit = { method, headers: { ...(headers ?? {}) } }
    if (method === 'GET') {
      const search = new URLSearchParams()
      for (const [key, value] of Object.entries(payload)) {
        if (value === undefined || value === null || value === '') {
          continue
        }
        search.set(key, String(value))
      }
      url = search.size > 0 ? `${url}?${search.toString()}` : url
    } else {
      init.headers = { 'Content-Type': 'application/json', ...(headers ?? {}) }
      init.body = JSON.stringify(payload)
    }
    const response = await fetchFn(url, init)
    if (!response.ok) {
      throw new Error('通知服务不可用')
    }
    return unwrapResponse(await response.json())
  }

  return {
    load: async (query: NotificationQuery): Promise<unknown> => {
      const params: Record<string, unknown> = {
        page: query.page ?? 1,
        size: query.pageSize ?? 20,
      }
      const type = query.type !== undefined && query.type !== 'all' ? REQUEST_TYPE[query.type] : undefined
      if (type !== undefined) {
        params.type = type
      }
      if (query.read === 'unread') {
        params.is_read = false
      } else if (query.read === 'read') {
        params.is_read = true
      }
      return request('GET', '/notifications', params)
    },
    loadUnread: async (): Promise<number> => readCount(await request('GET', '/notifications/unread-count')),
    detail: async (id: string): Promise<unknown> =>
      request('GET', `/notifications/${encodeURIComponent(id)}`, { mark_read: true }),
    markRead: async (ids: readonly string[]): Promise<{ unreadCount?: number }> => ({
      unreadCount: readCount(await request('POST', '/notifications/read', { ids: [...ids] })),
    }),
    markAllRead: async (): Promise<{ unreadCount?: number }> => ({
      unreadCount: readCount(await request('POST', '/notifications/read-all')),
    }),
    remove: async (id: string): Promise<boolean> =>
      (await request('DELETE', `/notifications/${encodeURIComponent(id)}`)) === true,
  }
}
