/**
 * 帮助 HTTP 取数：`GET /api/v1/help/context`（08_02 五级解析；09_02 补 `anchor_found`）。
 *
 * 只做请求与解包；归一与上下文键归核心 `domain/help.ts`，状态机归 `BaseHelpContext`。
 * 页面 / 顶栏经宿主装配取默认实例（`createHttpHelpFetcher(sourceEndpoint('platform'))`）。
 */

import type { HelpContextFetcher } from '@bms/core'

/** 适配器选项。 */
export interface HelpHttpOptions {
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
        throw new Error(typeof record.message === 'string' && record.message !== '' ? record.message : '帮助服务不可用')
      }
      return record.data
    }
  }
  return payload
}

/**
 * 创建帮助 HTTP 取数器。
 *
 * @param options 适配器选项。
 * @returns 帮助取数器（`buildHelpQuery` 已排好的线参数原样透传）。
 */
export function createHttpHelpFetcher(options: HelpHttpOptions = {}): HelpContextFetcher {
  const endpoint = (options.endpoint ?? '/api/v1').replace(/\/+$/, '')

  return async (query: Record<string, string>): Promise<unknown> => {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      throw new Error('帮助服务不可用')
    }
    const headers = typeof options.headers === 'function' ? options.headers() : options.headers
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(query)) {
      if (value === '') {
        continue
      }
      search.set(key, value)
    }
    const url = search.size > 0 ? `${endpoint}/help/context?${search.toString()}` : `${endpoint}/help/context`
    const response = await fetchFn(url, { method: 'GET', headers: { ...(headers ?? {}) } })
    if (!response.ok) {
      throw new Error('帮助服务不可用')
    }
    return unwrapResponse(await response.json())
  }
}
