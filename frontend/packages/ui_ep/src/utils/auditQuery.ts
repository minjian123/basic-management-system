/**
 * 审计 HTTP 取数适配器：`GET /api/v1/audit/data-changes`（列表 / 详情）与 `GET /api/v1/audit/chain/verify`。
 *
 * 只做请求与解包；归一与分组归核心 `domain/audit.ts`，渲染归 `AuditDiff`（纯 props）。
 */

/** 列表查询条件（camelCase；线参数转 snake_case）。 */
export interface AuditPageQuery {
  /** 被审计逻辑表名。 */
  tableName?: string
  /** 被审计记录主键。 */
  recordId?: string
  /** 操作人主键。 */
  operatorId?: string
  /** 业务域。 */
  domainKey?: string
  /** 事件时间下界（ISO）。 */
  occurredFrom?: string
  /** 事件时间上界（ISO）。 */
  occurredTo?: string
  /** 页码（自 1）。 */
  page?: number
  /** 页长。 */
  size?: number
}

/** 审计取数适配器。 */
export interface AuditQueryAdapter {
  /** 列表分页（字段级变更行）。 */
  page(query: AuditPageQuery): Promise<unknown>
  /** 单条审计详情（含链字段）。 */
  detail(id: string): Promise<unknown>
  /** 链校验（月份逗号分隔；空 = 台账全部）。 */
  verify(months?: string): Promise<unknown>
}

/** 适配器选项。 */
export interface AuditHttpOptions {
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
        throw new Error(typeof record.message === 'string' && record.message !== '' ? record.message : '审计服务不可用')
      }
      return record.data
    }
  }
  return payload
}

/**
 * 创建审计 HTTP 取数适配器。
 *
 * @param options 适配器选项。
 * @returns 审计取数适配器。
 */
export function createHttpAuditQuery(options: AuditHttpOptions = {}): AuditQueryAdapter {
  const endpoint = (options.endpoint ?? '/api/v1').replace(/\/+$/, '')

  /**
   * 发起 GET 请求并解包。
   *
   * @param path 路径（相对端点前缀）。
   * @param params 查询参数。
   * @returns 数据体。
   */
  async function get(path: string, params: Record<string, unknown> = {}): Promise<unknown> {
    const fetchFn = globalThis.fetch
    if (typeof fetchFn !== 'function') {
      throw new Error('审计服务不可用')
    }
    const headers = typeof options.headers === 'function' ? options.headers() : options.headers
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') {
        continue
      }
      search.set(key, String(value))
    }
    const url = search.size > 0 ? `${endpoint}${path}?${search.toString()}` : `${endpoint}${path}`
    const response = await fetchFn(url, { method: 'GET', headers: { ...(headers ?? {}) } })
    if (!response.ok) {
      throw new Error('审计服务不可用')
    }
    return unwrapResponse(await response.json())
  }

  return {
    page: async (query: AuditPageQuery): Promise<unknown> =>
      get('/audit/data-changes', {
        table_name: query.tableName,
        record_id: query.recordId,
        operator_id: query.operatorId,
        domain_key: query.domainKey,
        occurred_from: query.occurredFrom,
        occurred_to: query.occurredTo,
        page: query.page ?? 1,
        size: query.size ?? 20,
      }),
    detail: async (id: string): Promise<unknown> => get(`/audit/data-changes/${encodeURIComponent(id)}`),
    verify: async (months?: string): Promise<unknown> => get('/audit/chain/verify', { months }),
  }
}
