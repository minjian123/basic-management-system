// kiwi_id: 2232
/** SSO 端点封装用例（05_01）：入口清单服务段寻址 + 授权跳转地址构造。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchSsoProviders, ssoAuthorizeUrl } from '@/api/identity'

const requestMock = vi.fn()

beforeEach(() => {
  requestMock.mockReset()
  requestMock.mockResolvedValue({ items: [] })
  configureRequestAdapter({ request: requestMock })
})

/** 取第 `index` 次请求配置。 */
function callAt(index: number): RequestConfig {
  return requestMock.mock.calls[index]?.[0] as RequestConfig
}

describe('SSO 端点封装（Kiwi 2232）', () => {
  it('入口清单经服务段寻址（GET，无租户时不带查询参数）', async () => {
    await fetchSsoProviders()
    expect(callAt(0).method).toBe('GET')
    expect(callAt(0).url).toBe('/api/identity/v1/auth/sso/providers')
    expect(callAt(0).params).toBeUndefined()
  })

  it('入口清单携带租户查询参数（空串与 null 视同未携带）', async () => {
    await fetchSsoProviders('acme')
    expect(callAt(0).params).toEqual({ tenant: 'acme' })

    await fetchSsoProviders('')
    expect(callAt(1).params).toBeUndefined()

    await fetchSsoProviders(null)
    expect(callAt(2).params).toBeUndefined()
  })

  it('授权地址为站内服务段路径（顶层跳转由后端 302 到外部 IdP）', () => {
    expect(ssoAuthorizeUrl('keycloak', 'acme')).toBe('/api/identity/v1/auth/sso/keycloak/authorize?tenant=acme')
    expect(ssoAuthorizeUrl('keycloak')).toBe('/api/identity/v1/auth/sso/keycloak/authorize')
    expect(ssoAuthorizeUrl('keycloak', '')).toBe('/api/identity/v1/auth/sso/keycloak/authorize')
    expect(ssoAuthorizeUrl('key cloack', 'acme')).toBe('/api/identity/v1/auth/sso/key%20cloack/authorize?tenant=acme')
    expect(requestMock).not.toHaveBeenCalled()
  })
})
