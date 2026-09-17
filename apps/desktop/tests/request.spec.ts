/** 请求层用例（Kiwi 717）：拦截器 / 解包 / 401 收敛刷新 / 幂等键（双端同款）。 */

import { AxiosError, AxiosHeaders } from 'axios'
import type { AxiosResponse } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { configureHttpAdapter, resetHttpAdapter } from '@/api/adapter'
import { BaseApi } from '@/api/base'
import { ApiError, AUTH_SESSION_CODE, errorMessage, NETWORK_ERROR_CODE } from '@/api/error'
import { http } from '@/api/http'
import { request } from '@/api/request'
import { tokenManager } from '@/api/token'
import { resetFrontendBaseConfig, setFrontendSinks } from '@/base/BaseFrontend'

function asResponse<T>(data: T, status = 200): AxiosResponse<T> {
  return { data, status } as unknown as AxiosResponse<T>
}

function unauthorized(url = '/demo/items'): AxiosError {
  return new AxiosError(
    'unauthorized',
    'ERR_BAD_REQUEST',
    { url, headers: new AxiosHeaders(), metadata: {} } as never,
    undefined,
    {
      status: 401,
    } as AxiosResponse,
  )
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

/** 演示模块 API（暴露 protected 方法） */
class DemoApi extends BaseApi {
  create(body: object, idempotencyKey?: string): Promise<unknown> {
    return this.post('/items', body, idempotencyKey ? { idempotencyKey } : undefined)
  }

  fetch(params?: object): Promise<unknown> {
    return this.get('/items', params)
  }
}

describe('请求层（Kiwi 717）', () => {
  beforeEach(() => {
    setFrontendSinks({ log: () => {}, error: () => {} })
  })

  afterEach(() => {
    setFrontendSinks({ log: undefined, error: undefined })
    resetFrontendBaseConfig()
    resetHttpAdapter()
    tokenManager.clear()
    vi.restoreAllMocks()
  })

  it('① request：解包 data 与 raw 完整响应', async () => {
    const spy = vi.spyOn(http, 'request').mockResolvedValue(asResponse({ code: 0, message: 'ok', data: { id: '1' } }))
    expect(await request({ url: '/x' })).toEqual({ id: '1' })
    const raw = await request<{ id: string }, { raw: true }>({ url: '/x' }, { raw: true })
    expect(raw).toEqual({ code: 0, message: 'ok', data: { id: '1' } })
    expect(spy).toHaveBeenCalledTimes(2)
  })

  it('② 业务错误：ApiError 字段 + 默认提示 + silent 跳过', async () => {
    const notify = vi.fn()
    configureHttpAdapter({ notify })
    vi.spyOn(http, 'request').mockResolvedValueOnce(
      asResponse({ code: 40001, message: '配置错误', data: { field: 'a' } }),
    )
    const failure = await request({ url: '/x' }).catch((error: unknown) => error)
    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({ code: 40001, httpStatus: 200, details: { field: 'a' } })
    expect(notify).toHaveBeenCalledTimes(1)

    notify.mockClear()
    vi.spyOn(http, 'request').mockResolvedValueOnce(asResponse({ code: 40001, message: '配置错误', data: null }))
    await expect(request({ url: '/x' }, { silent: true })).rejects.toBeInstanceOf(ApiError)
    expect(notify).not.toHaveBeenCalled()
  })

  it('③ 请求拦截器：Authorization / Accept-Language / X-Request-Id / 写方法幂等键', () => {
    tokenManager.setAccessToken('token-1')
    const config = { url: '/x', method: 'post', headers: new AxiosHeaders(), metadata: {} }
    const returned = requestHandlers()[0]?.fulfilled?.(config as never) as typeof config
    expect(returned).toBe(config)
    expect(config.headers.get('Authorization')).toBe('Bearer token-1')
    expect(config.headers.get('Accept-Language')).toBeTruthy()
    expect(config.headers.get('X-Request-Id')).toBeTruthy()
    expect(config.headers.get('Idempotency-Key')).toBeTruthy()

    const readConfig = { url: '/y', method: 'get', headers: new AxiosHeaders(), metadata: {} }
    requestHandlers()[0]?.fulfilled?.(readConfig as never)
    expect(readConfig.headers.get('Idempotency-Key')).toBeFalsy()
  })

  it('④ 401 占位降级（未接入刷新）：清会话 + 跳登录 + ApiError(20001)', async () => {
    const redirectToLogin = vi.fn()
    configureHttpAdapter({ redirectToLogin })
    tokenManager.setAccessToken('stale')
    const result = responseHandlers()[0]?.rejected?.(unauthorized()) as Promise<never>
    await expect(result).rejects.toMatchObject({ code: AUTH_SESSION_CODE, httpStatus: 401 })
    expect(tokenManager.hasToken()).toBe(false)
    expect(redirectToLogin).toHaveBeenCalled()
  })

  it('⑤ 401 并发收敛：三请求仅刷新一次并各重放一次（新 token）', async () => {
    let refreshCount = 0
    configureHttpAdapter({
      refreshHandler: async () => {
        refreshCount += 1
        await Promise.resolve()
        return 'new-token'
      },
    })
    tokenManager.setAccessToken('stale')
    const replay = vi.spyOn(http, 'request').mockResolvedValue(asResponse({ code: 0, message: 'ok', data: null }))
    const configs = ['/a', '/b', '/c'].map((url) => ({ url, headers: new AxiosHeaders(), metadata: {} }))
    const results = configs.map((config) =>
      responseHandlers()[0]?.rejected?.(
        new AxiosError('401', 'ERR_BAD_REQUEST', config as never, undefined, { status: 401 } as AxiosResponse),
      ),
    )
    await Promise.all(results)
    expect(refreshCount).toBe(1)
    expect(replay).toHaveBeenCalledTimes(3)
    for (const config of configs) {
      expect((config as { __authRetried?: boolean }).__authRetried).toBe(true)
      expect(config.headers.get('Authorization')).toBe('Bearer new-token')
    }
    expect(tokenManager.getAccessToken()).toBe('new-token')
  })

  it('⑥ 刷新失败：清会话 + 跳登录', async () => {
    const redirectToLogin = vi.fn()
    configureHttpAdapter({ refreshHandler: async () => null, redirectToLogin })
    tokenManager.setAccessToken('stale')
    const result = responseHandlers()[0]?.rejected?.(unauthorized()) as Promise<never>
    await expect(result).rejects.toMatchObject({ code: AUTH_SESSION_CODE })
    expect(tokenManager.hasToken()).toBe(false)
    expect(redirectToLogin).toHaveBeenCalled()
  })

  it('⑦ errorMessage：i18n → 后端文案 → 通用兜底', () => {
    expect(errorMessage(19001)).toBe('该功能尚未实现')
    expect(errorMessage('network')).toBe('网络异常，请检查网络')
    expect(errorMessage(999999, '后端文案')).toBe('后端文案')
    expect(errorMessage(999999)).toBe('操作失败，请稍后重试')
  })

  it('⑧ BaseApi：写方法自动幂等键（显式优先）、读方法不带', async () => {
    const captured: { headers?: Record<string, unknown> }[] = []
    vi.spyOn(http, 'request').mockImplementation(async (config) => {
      captured.push(config as { headers?: Record<string, unknown> })
      return asResponse({ code: 0, message: 'ok', data: null })
    })
    const api = new DemoApi('/demo')
    await api.create({})
    await api.fetch({})
    await api.create({}, 'fixed-key')
    expect((captured[0]?.headers as Record<string, string>)['Idempotency-Key']).toBeTruthy()
    expect((captured[1]?.headers as Record<string, string>)['Idempotency-Key']).toBeUndefined()
    expect((captured[2]?.headers as Record<string, string>)['Idempotency-Key']).toBe('fixed-key')
  })

  it('⑨ 403 / 5xx / 结构异常归一', async () => {
    const redirectToForbidden = vi.fn()
    const notify = vi.fn()
    configureHttpAdapter({ redirectToForbidden, notify })

    const forbidden = responseHandlers()[0]?.rejected?.(
      new AxiosError(
        'forbidden',
        'ERR_BAD_RESPONSE',
        { url: '/x', headers: new AxiosHeaders(), metadata: {} } as never,
        undefined,
        { status: 403, headers: {} } as AxiosResponse,
      ),
    ) as Promise<never>
    await expect(forbidden).rejects.toMatchObject({ code: 30001, httpStatus: 403 })
    expect(redirectToForbidden).toHaveBeenCalled()

    const serverError = new AxiosError(
      'server',
      'ERR_BAD_RESPONSE',
      { url: '/x', headers: new AxiosHeaders(), metadata: {} } as never,
      undefined,
      {
        status: 500,
        headers: { 'x-trace-id': 'trace-1' },
      } as unknown as AxiosResponse,
    )
    const result = responseHandlers()[0]?.rejected?.(serverError) as Promise<never>
    await expect(result).rejects.toMatchObject({ code: 10000, traceId: 'trace-1' })
    expect(notify).toHaveBeenCalledWith(expect.stringContaining('trace-1'), 'error')

    vi.spyOn(http, 'request').mockResolvedValueOnce(asResponse(null))
    await expect(request({ url: '/x' })).rejects.toMatchObject({ code: NETWORK_ERROR_CODE })
  })
})
