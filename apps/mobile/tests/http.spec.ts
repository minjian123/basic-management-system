/** Axios 基线用例（Kiwi 25）：request 解包/错误、fetchAppInfo、请求与响应拦截器分支、根系上报。 */

import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { configureHttpAdapter, resetHttpAdapter } from '@/api/adapter'
import { ApiError, AUTH_SESSION_CODE, NETWORK_ERROR_CODE } from '@/api/error'
import { appInfoClient, fetchAppInfo, http } from '@/api/http'
import { request } from '@/api/request'
import { tokenManager } from '@/api/token'
import { resetHostSinks, setHostSinks, type HostErrorRecord } from '@/adapters/host-base'

function asResponse<T>(data: T): AxiosResponse<T> {
  return { data } as unknown as AxiosResponse<T>
}

function axiosError(status: number, message = 'error', config: Record<string, unknown> = {}): AxiosError {
  return new AxiosError(message, 'ERR_BAD_RESPONSE', { ...config, metadata: {} } as never, undefined, {
    status,
  } as AxiosResponse)
}

interface InterceptorHandlers {
  fulfilled?: (value: never) => unknown
  rejected?: (error: unknown) => unknown
}

function responseHandlers(): InterceptorHandlers[] {
  return (http.interceptors.response as unknown as { handlers: InterceptorHandlers[] }).handlers
}

function requestHandlers(): InterceptorHandlers[] {
  return (http.interceptors.request as unknown as { handlers: InterceptorHandlers[] }).handlers
}

describe('Axios 基线（Kiwi 25）', () => {
  beforeEach(() => {
    // 默认静音：错误上报断言在用例内自行注入 sink，避免控制台噪声
    setHostSinks({ log: () => {}, error: () => {} })
  })

  afterEach(() => {
    setHostSinks({ log: undefined, error: undefined })
    resetHostSinks()
    resetHttpAdapter()
    tokenManager.clear()
    vi.restoreAllMocks()
  })

  it('request：code=0 解包 data', async () => {
    vi.spyOn(http, 'request').mockResolvedValue(asResponse({ code: 0, message: 'ok', data: { id: '1' } }))
    expect(await request({ url: '/x' })).toEqual({ id: '1' })
  })

  it('request：code≠0 拒绝（message 与兜底文案）', async () => {
    vi.spyOn(http, 'request').mockResolvedValueOnce(asResponse({ code: 500, message: '业务失败', data: null }))
    await expect(request({ url: '/x' })).rejects.toThrow('业务失败')

    vi.spyOn(http, 'request').mockResolvedValueOnce(asResponse({ code: 500, message: '', data: null }))
    await expect(request({ url: '/x' })).rejects.toThrow('业务错误 500')
  })

  it('request：业务错误与 401 分支经根系上报', async () => {
    const errors: HostErrorRecord[] = []
    setHostSinks({ error: (record) => errors.push(record) })
    const redirectToLogin = vi.fn()
    configureHttpAdapter({ redirectToLogin })

    vi.spyOn(http, 'request').mockResolvedValueOnce(asResponse({ code: 500, message: '业务失败', data: null }))
    await expect(request({ url: '/x' })).rejects.toThrow('业务失败')
    expect(errors[0]).toMatchObject({
      ns: 'http',
      identifier: 'request',
      message: '业务失败',
      meta: { code: 500, url: '/x' },
    })

    tokenManager.setAccessToken('stale-token')
    const unauthorized = axiosError(401, 'unauthorized')
    const rejected = responseHandlers()[0]?.rejected?.(unauthorized) as Promise<never>
    await expect(rejected).rejects.toMatchObject({ code: AUTH_SESSION_CODE })
    expect(tokenManager.hasToken()).toBe(false)
    expect(redirectToLogin).toHaveBeenCalled()
    expect(errors[1]).toMatchObject({
      ns: 'http',
      name: 'AxiosError',
      meta: { status: 401, code: AUTH_SESSION_CODE },
    })
  })

  it('fetchAppInfo：解析 /info 应用信息', async () => {
    vi.spyOn(appInfoClient, 'get').mockResolvedValue(
      asResponse({ code: 0, message: 'ok', data: { name: 'BMS 基础管理系统', version: '0.1.0' } }),
    )
    expect(await fetchAppInfo()).toEqual({ name: 'BMS 基础管理系统', version: '0.1.0' })
  })

  it('请求拦截器：透传 config 并注入请求标识', () => {
    tokenManager.setAccessToken('token-1')
    const config = { url: '/x', headers: undefined as never, metadata: undefined }
    const returned = requestHandlers()[0]?.fulfilled?.(config as never) as typeof config & {
      headers: { get: (name: string) => string | undefined }
    }
    expect(returned).toBe(config)
    expect(returned.headers.get('Authorization')).toBe('Bearer token-1')
    expect(returned.headers.get('X-Request-Id')).toBeTruthy()
  })

  it('响应拦截器：成功透传响应', () => {
    const response = asResponse({ code: 0, message: 'ok', data: null })
    expect(responseHandlers()[0]?.fulfilled?.(response as never)).toBe(response)
  })

  it('响应拦截器：HTTP 错误归一为 ApiError（401 / 5xx / 网络）', async () => {
    const unauthorized = responseHandlers()[0]?.rejected?.(axiosError(401)) as Promise<never>
    await expect(unauthorized).rejects.toMatchObject({ code: AUTH_SESSION_CODE, httpStatus: 401 })

    const serverError = responseHandlers()[0]?.rejected?.(axiosError(500)) as Promise<never>
    await expect(serverError).rejects.toMatchObject({ code: 10000, httpStatus: 500 })

    const network = responseHandlers()[0]?.rejected?.(new Error('network')) as Promise<never>
    await expect(network).rejects.toBeInstanceOf(ApiError)
    await expect(responseHandlers()[0]?.rejected?.(new Error('network')) as Promise<never>).rejects.toMatchObject({
      code: NETWORK_ERROR_CODE,
    })
  })
})
