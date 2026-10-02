/** 认证端点封装用例（05_02 / Kiwi 2230）：服务段寻址、方法与载荷、生成类型消费。 */
// kiwi_id: 2230

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchCurrentUser, login, logout, refreshAccessToken } from '@/api/identity'

const requestMock = vi.fn()

beforeEach(() => {
  requestMock.mockReset()
  requestMock.mockResolvedValue({})
  configureRequestAdapter({ request: requestMock })
})

/** 取第 `index` 次请求配置。 */
function callAt(index: number): RequestConfig {
  return requestMock.mock.calls[index]?.[0] as RequestConfig
}

describe('认证端点封装（Kiwi 2230）', () => {
  it('四个端点按服务段寻址与方法发起', async () => {
    await login({ account: 'admin', password: 'secret' })
    await refreshAccessToken()
    await logout()
    await fetchCurrentUser()

    expect(requestMock.mock.calls.map((call) => `${(call[0] as RequestConfig).method} ${(call[0] as RequestConfig).url}`)).toEqual(
      [
        'POST /api/identity/v1/auth/login',
        'POST /api/identity/v1/auth/refresh',
        'POST /api/identity/v1/auth/logout',
        'GET /api/identity/v1/auth/me',
      ],
    )
  })

  it('登录携带请求体；会话动作不附幂等键', async () => {
    await login({ account: 'admin', password: 'secret' })
    await refreshAccessToken()
    await logout()

    expect(callAt(0).data).toEqual({ account: 'admin', password: 'secret' })
    expect(callAt(1).idempotencyKey).toBeUndefined()
    expect(callAt(2).idempotencyKey).toBeUndefined()
  })
})
