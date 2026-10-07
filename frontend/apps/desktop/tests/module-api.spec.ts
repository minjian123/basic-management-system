// kiwi_id: 2236
/**
 * 模块请求能力宿主实现用例（06_02）：模块 → `context.api` → 宿主请求层 → 适配器整链；
 * 401 单例静默刷新与重放对模块**透明**；刷新失败模块收到会话失效。
 */

import { ErrorCodes, configureRequestAdapter } from '@bms/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

import { SessionExpiredError } from '@/api/error'
import { createAxiosAdapter } from '@/api/http'
import { HostModuleApi, createModuleApi } from '@/api/module-api'
import { setTenantCode } from '@/api/tenant'

/** 401 的 axios 形态错误。 */
const UNAUTHORIZED = { isAxiosError: true, response: { status: 401 } }

/**
 * 统一响应成功载荷。
 *
 * @param data 数据。
 */
function ok<T>(data: T): { data: { code: number; message: string; data: T } } {
  return { data: { code: 0, message: 'ok', data } }
}

beforeEach(() => {
  requestMock.mockReset()
  useMock.mockClear()
  createMock.mockClear()
  setTenantCode(null)
})

describe('模块请求能力宿主实现（06_02 · Kiwi 2236）', () => {
  it('幂等键沿用宿主请求层口径（服务与路径入前缀）', () => {
    const key = new HostModuleApi().createIdempotencyKey('identity', '/auth/me')
    expect(key.startsWith('identity:/auth/me:')).toBe(true)
    expect(key.split(':').length).toBeGreaterThanOrEqual(4)
  })

  it('模块经 api 完成整链请求（服务段地址 + 统一解包返回业务数据）', async () => {
    requestMock.mockResolvedValueOnce(ok({ name: '张三' }))
    configureRequestAdapter(createAxiosAdapter())

    const result = await createModuleApi().get<{ name: string }>('identity', '/auth/me')

    expect(result).toEqual({ name: '张三' })
    expect(requestMock).toHaveBeenCalledWith({
      method: 'GET',
      url: '/api/identity/v1/auth/me',
      params: undefined,
      data: undefined,
      headers: {},
    })
  })

  it('写方法带幂等键头（宿主口径）', async () => {
    requestMock.mockResolvedValueOnce(ok(null))
    configureRequestAdapter(createAxiosAdapter())

    await createModuleApi().post('file', '/users', { name: '李四' })

    const call = requestMock.mock.calls[0]?.[0] as { headers: Record<string, string>; url: string }
    expect(call.url).toBe('/api/file/v1/users')
    expect(call.headers['Idempotency-Key']).toContain('file:/users:')
  })

  it('401 对模块透明：宿主单例刷新后重放，模块拿到数据（模块无任何 401 逻辑）', async () => {
    requestMock.mockRejectedValueOnce(UNAUTHORIZED)
    requestMock.mockResolvedValueOnce(ok({ name: '王五' }))
    const onRefresh = vi.fn().mockResolvedValue('new-token')
    configureRequestAdapter(createAxiosAdapter({ onRefresh }))

    const result = await createModuleApi().get<{ name: string }>('identity', '/auth/me')

    expect(result).toEqual({ name: '王五' })
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(requestMock).toHaveBeenCalledTimes(2)
  })

  it('刷新失败：模块收到会话失效错误（由模块自行降级）', async () => {
    requestMock.mockRejectedValue(UNAUTHORIZED)
    const onRefresh = vi.fn().mockResolvedValue(null)
    const onUnauthorized = vi.fn()
    configureRequestAdapter(createAxiosAdapter({ onRefresh, onUnauthorized }))

    await expect(createModuleApi().get('identity', '/auth/me')).rejects.toBeInstanceOf(SessionExpiredError)
    expect(onRefresh).toHaveBeenCalledTimes(1)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('业务失败：模块收到业务错误（HTTP 状态多为 200，按错误码判定）', async () => {
    requestMock.mockResolvedValueOnce({ data: { code: 10003, message: '冲突', data: null } })
    configureRequestAdapter(createAxiosAdapter())

    await expect(createModuleApi().get('platform', '/tenants')).rejects.toMatchObject({ code: 10003 })
  })

  it('非法服务键：抛 CAPABILITY_VIOLATION 且不发请求', async () => {
    configureRequestAdapter(createAxiosAdapter())

    await expect(createModuleApi().get('nope' as never)).rejects.toMatchObject({ code: ErrorCodes.CAPABILITY_VIOLATION })
    expect(requestMock).not.toHaveBeenCalled()
  })
})
