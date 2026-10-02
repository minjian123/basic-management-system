/** Axios 请求适配器用例（04-1-1 / 05_02 · Kiwi 2191 / 2230）：baseURL 收敛 / 令牌注入 / 响应解包 / 401 与错误 / 刷新重放与凭据。 */
// kiwi_id: 2191
// kiwi_id: 2230

import { getRequestAdapter, type RequestConfig } from '@bms/core'
import axios from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { requestMock, useMock, createMock } = vi.hoisted(() => {
  const requestMock = vi.fn()
  const useMock = vi.fn()
  const createMock = vi.fn(() => ({ interceptors: { request: { use: useMock } }, request: requestMock }))
  return { requestMock, useMock, createMock }
})

vi.mock('axios', () => ({
  default: {
    create: createMock,
    isAxiosError: (error: unknown) => Boolean((error as { isAxiosError?: boolean } | undefined)?.isAxiosError),
  },
}))

import { ApiError, SessionExpiredError } from '@/api/error'
import { createAxiosAdapter, installHttpAdapter } from '@/api/http'
import { setTenantCode } from '@/api/tenant'
import { setAccessToken } from '@/api/token'

/** 401 的 axios 形态错误。 */
const UNAUTHORIZED = { isAxiosError: true, response: { status: 401 } }

/** 统一响应成功载荷。 */
function ok<T>(data: T): { data: { code: number; message: string; data: T } } {
  return { data: { code: 0, message: 'ok', data } }
}

beforeEach(() => {
  requestMock.mockReset()
  useMock.mockClear()
  createMock.mockClear()
  setTenantCode(null)
})

afterEach(() => {
  setAccessToken(null)
  setTenantCode(null)
})

describe('createAxiosAdapter（Kiwi 2191）', () => {
  it('baseURL 收敛为 VITE_API_BASE（缺省同源 /）', () => {
    createAxiosAdapter()
    expect(createMock).toHaveBeenCalledWith({ baseURL: '/', timeout: 15_000 })
    expect(useMock).toHaveBeenCalledTimes(1)
  })

  it('请求拦截器按令牌注入 Authorization', () => {
    createAxiosAdapter()
    const interceptor = useMock.mock.calls[0]?.[0] as (config: {
      headers: Record<string, string>
    }) => { headers: Record<string, string> }
    const config = { headers: {} as Record<string, string> }
    expect(interceptor(config).headers.Authorization).toBeUndefined()
    setAccessToken('t1')
    expect(interceptor(config).headers.Authorization).toBe('Bearer t1')
  })

  it('成功请求解开统一响应', async () => {
    requestMock.mockResolvedValueOnce(ok({ id: 1 }))
    const adapter = createAxiosAdapter()
    const result = await adapter.request({ method: 'GET', url: '/api/platform/v1/x', params: { q: 1 } })
    expect(result).toEqual({ id: 1 })
    expect(requestMock).toHaveBeenCalledWith({
      method: 'GET',
      url: '/api/platform/v1/x',
      params: { q: 1 },
      data: undefined,
      headers: {},
    })
  })

  it('写方法携带幂等键', async () => {
    requestMock.mockResolvedValueOnce(ok(null))
    const adapter = createAxiosAdapter()
    await adapter.request({ method: 'POST', url: '/api/org/v1/y', idempotencyKey: 'k1' })
    const call = requestMock.mock.calls[0]?.[0] as RequestConfig & { headers: Record<string, string> }
    expect(call.headers['Idempotency-Key']).toBe('k1')
  })

  it('业务码非 0 抛 ApiError', async () => {
    requestMock.mockResolvedValueOnce({ data: { code: 10003, message: '冲突', data: null } })
    const adapter = createAxiosAdapter()
    await expect(adapter.request({ method: 'GET', url: '/api/platform/v1/x' })).rejects.toBeInstanceOf(ApiError)
  })

  it('401 → 会话失效 + onUnauthorized（未注入刷新处理器时占位口径）', async () => {
    requestMock.mockRejectedValueOnce(UNAUTHORIZED)
    const onUnauthorized = vi.fn()
    const adapter = createAxiosAdapter({ onUnauthorized })
    await expect(adapter.request({ method: 'GET', url: '/api/platform/v1/x' })).rejects.toBeInstanceOf(
      SessionExpiredError,
    )
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('非 axios 错误 → onError + ApiError(10001)', async () => {
    requestMock.mockRejectedValueOnce(new Error('boom'))
    const onError = vi.fn()
    const adapter = createAxiosAdapter({ onError })
    await expect(adapter.request({ method: 'GET', url: '/api/platform/v1/x' })).rejects.toMatchObject({ code: 10001 })
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it('installHttpAdapter 注入核心适配器', () => {
    installHttpAdapter({})
    expect(getRequestAdapter()).toBeDefined()
  })
})

describe('401 静默刷新与重放（Kiwi 2230）', () => {
  it('刷新成功后重放原请求（配置与幂等键原样）', async () => {
    requestMock.mockRejectedValueOnce(UNAUTHORIZED)
    requestMock.mockResolvedValueOnce(ok({ id: 7 }))
    const onRefresh = vi.fn().mockResolvedValue('new-token')
    const adapter = createAxiosAdapter({ onRefresh })

    const result = await adapter.request({ method: 'POST', url: '/api/platform/v1/x', idempotencyKey: 'k1' })

    expect(result).toEqual({ id: 7 })
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(requestMock).toHaveBeenCalledTimes(2)
    const replay = requestMock.mock.calls[1]?.[0] as RequestConfig & { headers: Record<string, string> }
    expect(replay.method).toBe('POST')
    expect(replay.url).toBe('/api/platform/v1/x')
    expect(replay.headers['Idempotency-Key']).toBe('k1')
  })

  it('并发 401 共享同一次刷新（onRefresh 仅一次），各自重放成功', async () => {
    requestMock.mockRejectedValueOnce(UNAUTHORIZED)
    requestMock.mockRejectedValueOnce(UNAUTHORIZED)
    requestMock.mockResolvedValue(ok({ ok: true }))
    const onRefresh = vi.fn(() => new Promise<string>((resolve) => setTimeout(() => resolve('new-token'), 0)))
    const adapter = createAxiosAdapter({ onRefresh })

    const results = await Promise.all([
      adapter.request({ method: 'GET', url: '/api/platform/v1/a' }),
      adapter.request({ method: 'GET', url: '/api/platform/v1/b' }),
    ])

    expect(results).toEqual([{ ok: true }, { ok: true }])
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(requestMock).toHaveBeenCalledTimes(4)
  })

  it('刷新失败（返回 null）→ 会话失效且不重放', async () => {
    requestMock.mockRejectedValue(UNAUTHORIZED)
    const onRefresh = vi.fn().mockResolvedValue(null)
    const onUnauthorized = vi.fn()
    const adapter = createAxiosAdapter({ onRefresh, onUnauthorized })

    await expect(adapter.request({ method: 'GET', url: '/api/platform/v1/x' })).rejects.toBeInstanceOf(
      SessionExpiredError,
    )
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(requestMock).toHaveBeenCalledTimes(1)
  })

  it('刷新抛错 → 会话失效（不递归刷新）', async () => {
    requestMock.mockRejectedValue(UNAUTHORIZED)
    const onRefresh = vi.fn().mockRejectedValue(new Error('refresh down'))
    const adapter = createAxiosAdapter({ onRefresh })

    await expect(adapter.request({ method: 'GET', url: '/api/platform/v1/x' })).rejects.toBeInstanceOf(
      SessionExpiredError,
    )
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(requestMock).toHaveBeenCalledTimes(1)
  })

  it('重放后仍 401 → 会话失效（每请求至多重放一次）', async () => {
    requestMock.mockRejectedValue(UNAUTHORIZED)
    const onRefresh = vi.fn().mockResolvedValue('new-token')
    const onUnauthorized = vi.fn()
    const adapter = createAxiosAdapter({ onRefresh, onUnauthorized })

    await expect(adapter.request({ method: 'GET', url: '/api/platform/v1/x' })).rejects.toBeInstanceOf(
      SessionExpiredError,
    )
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(requestMock).toHaveBeenCalledTimes(2)
  })

  it('认证端点自身 401 不触发刷新（防刷新循环）', async () => {
    const urls = ['/api/identity/v1/auth/login', '/api/identity/v1/auth/refresh', '/api/identity/v1/auth/logout']
    for (const url of urls) {
      requestMock.mockReset()
      requestMock.mockRejectedValue(UNAUTHORIZED)
      const onRefresh = vi.fn().mockResolvedValue('new-token')
      const adapter = createAxiosAdapter({ onRefresh })

      await expect(adapter.request({ method: 'POST', url })).rejects.toBeInstanceOf(SessionExpiredError)
      expect(onRefresh).not.toHaveBeenCalled()
      expect(requestMock).toHaveBeenCalledTimes(1)
    }
  })
})

describe('凭据与租户头口径（Kiwi 2230）', () => {
  /** 取装配后的请求拦截器。 */
  function interceptor(): (config: {
    headers: Record<string, string>
    url?: string
    withCredentials?: boolean
  }) => { headers: Record<string, string>; withCredentials?: boolean } {
    createAxiosAdapter()
    return useMock.mock.calls[0]?.[0] as never
  }

  it('仅认证端点（refresh / logout）开启凭据并注入 X-Tenant-ID', () => {
    const apply = interceptor()
    setTenantCode('demo')

    const refresh = apply({ headers: {}, url: '/api/identity/v1/auth/refresh' })
    expect(refresh.withCredentials).toBe(true)
    expect(refresh.headers['X-Tenant-ID']).toBe('demo')

    const logout = apply({ headers: {}, url: '/api/identity/v1/auth/logout' })
    expect(logout.withCredentials).toBe(true)

    const business = apply({ headers: {}, url: '/api/platform/v1/x' })
    expect(business.withCredentials).toBeUndefined()
    expect(business.headers['X-Tenant-ID']).toBeUndefined()
  })

  it('无租户编码时不注入 X-Tenant-ID（仍开启凭据）', () => {
    const apply = interceptor()
    const refresh = apply({ headers: {}, url: '/api/identity/v1/auth/refresh' })
    expect(refresh.withCredentials).toBe(true)
    expect(refresh.headers['X-Tenant-ID']).toBeUndefined()
  })
})

describe('axios 模块桩', () => {
  it('isAxiosError 判定', () => {
    expect(axios.isAxiosError({ isAxiosError: true })).toBe(true)
    expect(axios.isAxiosError(new Error('x'))).toBe(false)
  })
})
