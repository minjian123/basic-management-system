/** Axios 请求适配器用例（04-1-1 / Kiwi 2191）：baseURL 收敛 / 令牌注入 / 响应解包 / 401 与错误。 */
// kiwi_id: 2191

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
import { setAccessToken } from '@/api/token'

beforeEach(() => {
  requestMock.mockReset()
  useMock.mockClear()
  createMock.mockClear()
})

afterEach(() => {
  setAccessToken(null)
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
    requestMock.mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: { id: 1 } } })
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
    requestMock.mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: null } })
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

  it('401 → 会话失效 + onUnauthorized', async () => {
    requestMock.mockRejectedValueOnce({ isAxiosError: true, response: { status: 401 } })
    const onUnauthorized = vi.fn()
    const adapter = createAxiosAdapter({ onUnauthorized })
    await expect(adapter.request({ method: 'GET', url: '/api/platform/v1/x' })).rejects.toBeInstanceOf(SessionExpiredError)
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

describe('axios 模块桩', () => {
  it('isAxiosError 判定', () => {
    expect(axios.isAxiosError({ isAxiosError: true })).toBe(true)
    expect(axios.isAxiosError(new Error('x'))).toBe(false)
  })
})
