/**
 * 泛型请求函数：解开统一响应 `{code, message, data}`。
 *
 * - 成功：返回 `data`（`raw: true` 返回完整 `ApiResponse`）；
 * - 失败：抛 `ApiError`（HTTP 错误由 `http.ts` 拦截器归一，业务错误在本层判定），
 *   默认经适配 `notify` 提示（`silent: true` 跳过）并交根系上报。
 */

import type { AxiosRequestConfig } from 'axios'

import { useFrontendBase } from '@bms/vue'

import { hostBaseOptions } from '@/adapters/host-base'

import { getHttpAdapter } from './adapter'
import { ApiError, errorMessage, NETWORK_ERROR_CODE } from './error'
import { http } from './http'
import type { ApiResponse } from './types'

/** 请求层根系实例：统一日志与错误上报出口 */
const base = useFrontendBase(hostBaseOptions({ ns: 'http', identifier: 'request' }))

/** 请求选项 */
export interface RequestOptions {
  /** 不自动提示（调用方自行处理，如表单校验回显 / 登录失败） */
  silent?: boolean
  /** `true` 返回完整 `ApiResponse`（需读 `message` / `code`） */
  raw?: boolean
  /** 覆盖默认超时（毫秒） */
  timeout?: number
  /** 显式幂等键（写接口；缺省由 `BaseApi` 生成） */
  idempotencyKey?: string
  /** 取消信号（组件卸载 / 条件变化时中止在途请求） */
  signal?: AbortSignal
}

/** 业务错误提示（经适配注入；`silent` 跳过） */
function notifyError(message: string, silent: boolean): void {
  if (silent) {
    return
  }
  getHttpAdapter().notify?.(message, 'error')
}

export function request<T, O extends RequestOptions = RequestOptions>(
  config: AxiosRequestConfig,
  options?: O,
): Promise<O extends { raw: true } ? ApiResponse<T> : T> {
  return send<T>(config, options) as Promise<O extends { raw: true } ? ApiResponse<T> : T>
}

async function send<T>(config: AxiosRequestConfig, options: RequestOptions = {}): Promise<T | ApiResponse<T>> {
  const metadata = {
    ...((config.metadata as Record<string, unknown> | undefined) ?? {}),
    silent: options.silent === true,
  }
  const headers: Record<string, unknown> = { ...((config.headers as Record<string, unknown> | undefined) ?? {}) }
  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey
  }
  const response = await http.request<ApiResponse<T>>({
    ...config,
    headers: headers as AxiosRequestConfig['headers'],
    metadata,
    ...(options.timeout !== undefined ? { timeout: options.timeout } : {}),
    ...(options.signal !== undefined ? { signal: options.signal } : {}),
  })

  const payload = response.data as ApiResponse<T> | undefined
  if (!payload || typeof payload !== 'object' || typeof payload.code !== 'number') {
    const error = new ApiError({
      code: NETWORK_ERROR_CODE,
      message: errorMessage('network'),
      httpStatus: response.status,
      cause: payload,
    })
    notifyError(error.userMessage, options.silent === true)
    base.reportError(error, { code: error.code, url: config.url ?? '' })
    throw error
  }

  if (payload.code !== 0) {
    const error = new ApiError({
      code: payload.code,
      message: typeof payload.message === 'string' && payload.message ? payload.message : `业务错误 ${payload.code}`,
      httpStatus: response.status,
      details: payload.data,
    })
    notifyError(error.userMessage, options.silent === true)
    base.reportError(error, { code: payload.code, url: config.url ?? '' })
    throw error
  }

  return options.raw === true ? payload : payload.data
}
