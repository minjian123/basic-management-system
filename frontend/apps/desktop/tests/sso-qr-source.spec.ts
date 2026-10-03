// kiwi_id: 2233
/** 宿主扫码登录状态源用例（05_04）：真实取授权 URL + 占位轮询零请求。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createHttpSsoQrSource } from '@/api/ssoQr'
import { setTenantCode } from '@/api/tenant'

const requestMock = vi.fn()

beforeEach(() => {
  requestMock.mockReset()
  requestMock.mockResolvedValue({ authorize_url: 'https://idp/authorize', state: 's1', expires_in: 30 })
  configureRequestAdapter({ request: requestMock })
  setTenantCode(null)
})

describe('宿主扫码登录状态源（Kiwi 2233）', () => {
  it('init 真实调用 authorize-url 端点', async () => {
    const source = createHttpSsoQrSource()
    const result = await source.init?.({ idpKey: 'wecom-1' })
    expect(result).toEqual({ authorize_url: 'https://idp/authorize', state: 's1', expires_in: 30 })
    expect((requestMock.mock.calls[0]?.[0] as RequestConfig).url).toBe(
      '/api/identity/v1/auth/sso/wecom-1/authorize-url',
    )
    expect(requestMock).toHaveBeenCalledTimes(1)
  })

  it('init 缺省使用持久化租户编码', async () => {
    setTenantCode('acme')
    const source = createHttpSsoQrSource()
    await source.init?.({ idpKey: 'wecom-1' })
    expect((requestMock.mock.calls[0]?.[0] as RequestConfig).params).toEqual({ tenant: 'acme' })
  })

  it('poll 占位恒 pending 且零请求（后端无扫码状态端点）', async () => {
    const source = createHttpSsoQrSource()
    requestMock.mockClear()
    const result = await source.poll?.({ idpKey: 'wecom-1', state: 's1', attempt: 1 })
    expect(result).toEqual({ status: 'pending' })
    expect(requestMock).not.toHaveBeenCalled()
  })
})
