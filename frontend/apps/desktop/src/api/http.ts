/**
 * Axios 统一实例与拦截器：token 注入、请求标识、统一响应放行与 HTTP 错误归一。
 *
 * - 成功（含业务码非 0）：放行响应，业务码判定在 `request.ts`（保持解包点单一）；
 * - HTTP 错误：401 静默刷新（并发收敛 + 单次重放；未接入刷新按会话失效占位）、
 *   403 / 404 / 409 / 5xx 归一为 `ApiError` 并提示；取消不提示不上报；
 * - 提示与跳转经 `adapter.ts` 注入（核心不依赖 UI 库与路由）。
 */

import axios, {
  AxiosHeaders,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import { useFrontendBase } from '@bms/vue'

import { hostBaseOptions } from '@/adapters/host-base'
import { i18n } from '@/i18n'

import { getHttpAdapter } from './adapter'
import {
  ApiError,
  AUTH_SESSION_CODE,
  CONFLICT_CODE,
  errorMessage,
  INTERNAL_ERROR_CODE,
  NETWORK_ERROR_CODE,
  NOT_FOUND_CODE,
  PARAM_CODE,
  PERMISSION_CODE,
} from './error'
import { tokenManager } from './token'
import type { ApiResponse } from './types'

/** 应用信息（backend 根信息接口，开发期经 Vite /info 代理重写）。 */
export interface AppInfo {
  name: string
  version: string
}

/** 请求层根系实例：统一日志与错误上报出口（`request.ts` 同源复用）。 */
const base = useFrontendBase(hostBaseOptions({ ns: 'http', identifier: 'request' }))

/** 根路径客户端（不挂 baseURL）：/info 连通探针；导出供单元测试注入。 */
export const appInfoClient: AxiosInstance = axios.create({ timeout: 10_000 })

export const http: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '/api',
  timeout: 15_000,
})

/** 401 不参与刷新流程的路径（登录 / 刷新 / 探针） */
const AUTH_WHITELIST = ['/auth/login', '/auth/refresh', '/info']

function isAuthWhitelisted(url: string): boolean {
  return AUTH_WHITELIST.some((path) => url.includes(path))
}

function setHeader(config: InternalAxiosRequestConfig, name: string, value: string): void {
  if (!(config.headers instanceof AxiosHeaders)) {
    config.headers = new AxiosHeaders(config.headers as Record<string, string>)
  }
  config.headers.set(name, value)
}

/** 生成请求标识 / 幂等键（`crypto.randomUUID` 兜底实现；`BaseApi` 与拦截器共用） */
export function createRequestId(): string {
  const cryptoApi = globalThis.crypto
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`
}

function currentPath(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  return `${window.location.pathname}${window.location.search}`
}

function currentLocale(): string {
  const locale = i18n.global.locale
  return typeof locale === 'string' ? locale : locale.value
}

function metadataOf(config?: AxiosRequestConfig): Record<string, unknown> {
  return (config?.metadata as Record<string, unknown> | undefined) ?? {}
}

function notify(config: AxiosRequestConfig | undefined, message: string): void {
  if (metadataOf(config).silent === true) {
    return
  }
  getHttpAdapter().notify?.(message, 'error')
}

function rejectWith(init: {
  code: number
  message: string
  httpStatus?: number
  traceId?: string
  cause?: unknown
}): Promise<never> {
  return Promise.reject(new ApiError(init))
}

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenManager.getAccessToken()
  if (token) {
    setHeader(config, 'Authorization', `Bearer ${token}`)
  }
  setHeader(config, 'Accept-Language', currentLocale())
  setHeader(config, 'X-Request-Id', createRequestId())
  if (!config.headers.get('Idempotency-Key')) {
    const method = (config.method ?? 'get').toUpperCase()
    if (method === 'POST' || method === 'PUT' || method === 'DELETE' || method === 'PATCH') {
      setHeader(config, 'Idempotency-Key', createRequestId())
    }
  }
  config.metadata = { ...metadataOf(config), startedAt: Date.now() }
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (axios.isCancel(error)) {
      // 主动取消：不提示、不上报、保持原始取消错误
      return Promise.reject(error)
    }
    if (!axios.isAxiosError(error)) {
      base.reportError(error, { code: NETWORK_ERROR_CODE })
      return rejectWith({ code: NETWORK_ERROR_CODE, message: errorMessage('network'), cause: error })
    }

    const config = error.config as (InternalAxiosRequestConfig & { __authRetried?: boolean }) | undefined
    const status = error.response?.status
    const url = config?.url ?? ''
    const payload = error.response?.data as { code?: unknown; message?: unknown } | undefined
    const payloadCode = typeof payload?.code === 'number' ? payload.code : undefined
    const payloadMessage = typeof payload?.message === 'string' && payload.message ? payload.message : undefined

    if (status === 401) {
      const skipRefresh = isAuthWhitelisted(url) || metadataOf(config).skipAuthRefresh === true
      if (config && !config.__authRetried && !skipRefresh) {
        const token = await tokenManager.refresh()
        if (token) {
          config.__authRetried = true
          setHeader(config, 'Authorization', `Bearer ${token}`)
          return http.request(config)
        }
        // 刷新失败 / 未接入（占位降级）：清会话 + 跳登录
        tokenManager.clear()
        getHttpAdapter().redirectToLogin?.(currentPath())
      }
      base.reportError(error, { status: 401, code: AUTH_SESSION_CODE })
      return rejectWith({
        code: AUTH_SESSION_CODE,
        message: payloadMessage ?? errorMessage('sessionExpired'),
        httpStatus: 401,
        cause: error,
      })
    }

    const traceId =
      (error.response?.headers?.['x-trace-id'] as string | undefined) ??
      (error.response?.headers?.['x-request-id'] as string | undefined)

    if (status === 403) {
      getHttpAdapter().redirectToForbidden?.()
      notify(config, errorMessage('forbidden'))
      base.reportError(error, { status, code: PERMISSION_CODE })
      return rejectWith({
        code: PERMISSION_CODE,
        message: errorMessage('forbidden'),
        httpStatus: 403,
        traceId,
        cause: error,
      })
    }
    if (status === 404) {
      notify(config, errorMessage('notFound'))
      base.reportError(error, { status, code: NOT_FOUND_CODE })
      return rejectWith({
        code: NOT_FOUND_CODE,
        message: errorMessage('notFound'),
        httpStatus: 404,
        traceId,
        cause: error,
      })
    }
    if (status === 409) {
      notify(config, errorMessage('conflict'))
      base.reportError(error, { status, code: CONFLICT_CODE })
      return rejectWith({
        code: CONFLICT_CODE,
        message: errorMessage('conflict'),
        httpStatus: 409,
        traceId,
        cause: error,
      })
    }
    if (status && status >= 500) {
      const message = traceId ? `${errorMessage('server')}（traceId: ${traceId}）` : errorMessage('server')
      notify(config, message)
      base.reportError(error, { status, code: INTERNAL_ERROR_CODE, traceId })
      return rejectWith({
        code: INTERNAL_ERROR_CODE,
        message,
        httpStatus: status,
        traceId,
        cause: error,
      })
    }

    // 其余 HTTP 错误（400 / 422 等）与无响应网络错误
    const code = error.response ? (payloadCode ?? PARAM_CODE) : NETWORK_ERROR_CODE
    const message = payloadMessage ?? (error.response ? errorMessage(code) : errorMessage('network'))
    notify(config, message)
    base.reportError(error, { status: status ?? 0, code })
    return rejectWith({ code, message, httpStatus: status ?? 0, traceId, cause: error })
  },
)

/** 获取 backend 应用信息（开发期 /info 代理重写至 backend 根）。 */
export async function fetchAppInfo(): Promise<AppInfo> {
  const response = await appInfoClient.get<ApiResponse<AppInfo>>('/info')
  return response.data.data
}
