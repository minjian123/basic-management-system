// kiwi_id: 2233
/** 扫码授权 URL 端点封装用例（05_04）：服务段寻址 + 租户参数 + idpKey 编码。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSsoAuthorizeInfo } from '@/api/identity'

const requestMock = vi.fn()

beforeEach(() => {
  requestMock.mockReset()
  requestMock.mockResolvedValue({ authorize_url: 'https://idp/authorize', state: 's', expires_in: 30 })
  configureRequestAdapter({ request: requestMock })
})

/** 取第 `index` 次请求配置。 */
function callAt(index: number): RequestConfig {
  return requestMock.mock.calls[index]?.[0] as RequestConfig
}

describe('扫码授权 URL 端点封装（Kiwi 2233）', () => {
  it('经服务段寻址（GET）并携带租户参数', async () => {
    await fetchSsoAuthorizeInfo('wecom-1', 'acme')
    expect(callAt(0).method).toBe('GET')
    expect(callAt(0).url).toBe('/api/identity/v1/auth/sso/wecom-1/authorize-url')
    expect(callAt(0).params).toEqual({ tenant: 'acme' })
  })

  it('无租户（undefined / null / 空串）不带查询参数', async () => {
    await fetchSsoAuthorizeInfo('wecom-1')
    expect(callAt(0).params).toBeUndefined()

    await fetchSsoAuthorizeInfo('wecom-1', null)
    expect(callAt(1).params).toBeUndefined()

    await fetchSsoAuthorizeInfo('wecom-1', '')
    expect(callAt(2).params).toBeUndefined()
  })

  it('idpKey 经 URL 编码', async () => {
    await fetchSsoAuthorizeInfo('we com')
    expect(callAt(0).url).toBe('/api/identity/v1/auth/sso/we%20com/authorize-url')
  })
})
