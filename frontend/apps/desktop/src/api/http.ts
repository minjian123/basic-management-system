/**
 * 请求层：Axios 适配器装配（token 注入 / 统一响应解包 / 401 静默刷新与重放 / 凭据口径）。
 *
 * - **access 仅内存**：请求拦截器统一注入 `Authorization`；
 * - **401 静默刷新**：单例刷新（并发 401 共享同一次刷新）→ 成功后**重放原请求**（配置原样，
 *   含 `Idempotency-Key`）→ 失败清会话并跳登录（宿主钩子）；刷新请求自身、登录与已重放请求
 *   一律不触发刷新（**防刷新循环**）；
 * - **凭据口径**：仅认证端点（`/auth/refresh`、`/auth/logout`）开启 `withCredentials` 并注入
 *   `X-Tenant-ID`，其余请求不带 cookie；
 * - **未注入刷新处理器时**按会话失效占位（清会话 + 跳登录、不发刷新请求）；
 * - **401 优先保留业务码**：统一响应体带 `code`（如登录失败 `20002`、会话失效 `20001` / `20012`）时按业务码上抛
 *   `ApiError`（交调用方走文案表）；仅当无业务码（网关 / 空体 401）才上抛 `SessionExpiredError`。
 */

import {
  configureRequestAdapter,
  serviceUrl,
  type ApiResponse,
  type RequestAdapter,
  type RequestConfig,
} from '@bms/core'
import axios from 'axios'

import { ApiError, SessionExpiredError } from './error'
import { unwrap } from './response'
import { getTenantCode } from './tenant'
import { getAccessToken } from './token'

/** 宿主注入钩子。 */
export interface HttpHooks {
  /** 刷新处理器（缺省占位：未注入时 401 按会话失效处理，不发刷新请求）；返回新 access，无会话返回 `null`。 */
  onRefresh?: () => Promise<string | null>
  /** 401 处理（缺省占位：由宿主注入清会话 + 跳登录）。 */
  onUnauthorized?: () => void
  /** 错误上报。 */
  onError?: (error: unknown) => void
}

/** 需携带 refresh cookie 的认证端点（仅此二者；其余请求一律不带 cookie）。 */
const CREDENTIAL_PATHS = ['/auth/refresh', '/auth/logout'] as const

/** 不参与 401 静默刷新的端点（认证动作本身；防刷新循环）。 */
const NO_REFRESH_PATHS = ['/auth/login', '/auth/refresh', '/auth/logout'] as const

/** 租户编码请求头（refresh / logout 的租户上下文来源之一）。 */
const TENANT_HEADER = 'X-Tenant-ID'

/**
 * URL 是否命中认证端点集合（与 `serviceUrl` 精确比对）。
 *
 * @param url 请求地址。
 * @param paths 端点子路径集合。
 */
function matchesIdentityPaths(url: string, paths: readonly string[]): boolean {
  return paths.some((path) => url === serviceUrl('identity', path))
}

/** 模块级单例刷新（并发 401 共享同一次刷新；完成后清空以便后续再次刷新）。 */
let refreshPromise: Promise<boolean> | null = null

/**
 * 从 401 响应体读取业务错误（统一响应 `{ code, message }`）。
 *
 * @param body 响应体（可能为空 / 非统一响应）。
 * @returns 业务码与文案；无有效业务码返回 `undefined`。
 */
function readBusinessError(body: unknown): { code: number; message: string } | undefined {
  if (typeof body !== 'object' || body === null) {
    return undefined
  }
  const record = body as Record<string, unknown>
  const code = record['code']
  if (typeof code !== 'number' || code === 0) {
    return undefined
  }
  return { code, message: typeof record['message'] === 'string' ? record['message'] : '' }
}

/**
 * 创建 Axios 请求适配器。
 *
 * @param hooks 宿主钩子。
 */
export function createAxiosAdapter(hooks: HttpHooks = {}): RequestAdapter {
  const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE ?? '/', timeout: 15_000 })
  client.interceptors.request.use((config) => {
    const token = getAccessToken()
    if (token !== null) {
      config.headers.Authorization = `Bearer ${token}`
    }
    const url = typeof config.url === 'string' ? config.url : ''
    if (matchesIdentityPaths(url, CREDENTIAL_PATHS)) {
      config.withCredentials = true
      const tenant = getTenantCode()
      if (tenant !== null) {
        config.headers[TENANT_HEADER] = tenant
      }
    }
    return config
  })

  /**
   * 单例刷新：并发调用共享同一次刷新；未注入处理器 / 刷新失败一律返回 `false`。
   */
  const refreshOnce = (): Promise<boolean> => {
    const refresh = hooks.onRefresh
    if (refresh === undefined) {
      return Promise.resolve(false)
    }
    refreshPromise ??= refresh()
      .then((token) => token !== null)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null
      })
    return refreshPromise
  }

  /**
   * 执行一次请求（`retried` 标记是否已重放过，用于「每请求至多重放一次」）。
   *
   * @param request 请求配置。
   * @param retried 是否已重放。
   */
  async function execute<T>(request: RequestConfig, retried: boolean): Promise<T> {
    try {
      const headers: Record<string, string> = { ...request.headers }
      if (request.idempotencyKey !== undefined) {
        headers['Idempotency-Key'] = request.idempotencyKey
      }
      const response = await client.request<ApiResponse<T>>({
        method: request.method,
        url: request.url,
        params: request.params,
        data: request.data,
        headers,
      })
      return unwrap(response.data)
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        const retryable = !retried && !matchesIdentityPaths(request.url, NO_REFRESH_PATHS)
        if (retryable && (await refreshOnce())) {
          return execute<T>(request, true)
        }
        hooks.onUnauthorized?.()
        // **401 优先按业务码上抛**：登录失败（`20002`「账号或密码错误」）、验证码（`20101`）等一律走文案表；
        // 旧口径把 401 全量转 `SessionExpiredError`，会把「密码错误」显示成「会话已失效」。
        const business = readBusinessError(error.response.data)
        throw business === undefined
          ? new SessionExpiredError()
          : new ApiError(business.code, business.message, { userMessage: business.message })
      }
      hooks.onError?.(error)
      if (error instanceof ApiError) {
        throw error
      }
      throw new ApiError(10001, error instanceof Error ? error.message : '请求失败')
    }
  }

  return {
    request<T>(request: RequestConfig): Promise<T> {
      return execute<T>(request, false)
    },
  }
}

/**
 * 装配请求适配器到核心（宿主入口调用一次）。
 *
 * @param hooks 宿主钩子。
 */
export function installHttpAdapter(hooks: HttpHooks = {}): void {
  configureRequestAdapter(createAxiosAdapter(hooks))
}
