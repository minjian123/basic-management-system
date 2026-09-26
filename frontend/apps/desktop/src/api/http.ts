/** 请求层：Axios 适配器装配（token 注入 / 统一响应解包 / 401 会话失效）。 */

import { configureRequestAdapter, type ApiResponse, type RequestAdapter, type RequestConfig } from '@bms/core'
import axios from 'axios'

import { ApiError, SessionExpiredError } from './error'
import { unwrap } from './response'
import { getAccessToken } from './token'

/** 宿主注入钩子。 */
export interface HttpHooks {
  /** 401 处理（缺省占位：由宿主注入清会话 + 跳登录）。 */
  onUnauthorized?: () => void
  /** 错误上报。 */
  onError?: (error: unknown) => void
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
    return config
  })
  return {
    async request<T>(request: RequestConfig): Promise<T> {
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
          hooks.onUnauthorized?.()
          throw new SessionExpiredError()
        }
        hooks.onError?.(error)
        if (error instanceof ApiError) {
          throw error
        }
        throw new ApiError(10001, error instanceof Error ? error.message : '请求失败')
      }
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
