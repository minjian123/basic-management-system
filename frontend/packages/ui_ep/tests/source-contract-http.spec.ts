// kiwi_id: 2524
/** 数据源 HTTP 契约（09_01）：字典 / 远程字典 / 验证码三族端点、方法与入参。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { createHttpCaptchaSource, createHttpDictRemoteSource, createHttpDictSource } from '../src'

/** 统一响应包装。 */
function wrap(data: unknown): unknown {
  return { code: 0, message: '', data }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('数据源 HTTP 契约（09_01）', () => {
  it('字典：单类型 GET /dicts/{type} 与批量 POST /dicts/batch', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void url
      void init
      return { ok: true, json: async () => wrap({ version: 3, items: [], has_more: false, total: 0 }) }
    })
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpDictSource({ endpoint: '/api/platform/v1', headers: { Authorization: 'Bearer t' } })

    await source.getType?.({ dataSourceKey: 'user_status', version: 2 })
    const [typeUrl, typeInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(typeUrl).toContain('/api/platform/v1/dicts/user_status?')
    expect(typeUrl).toContain('version=2')
    expect(typeInit.method).toBe('GET')

    await source.batch?.({ types: ['user_status', 'dept_type'], version: 3 })
    const [batchUrl, batchInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(batchUrl).toBe('/api/platform/v1/dicts/batch')
    expect(batchInit.method).toBe('POST')
    expect(JSON.parse(String(batchInit.body))).toMatchObject({ types: ['user_status', 'dept_type'], version: 3 })
  })

  it('远程字典：用户查询走 /data-source/users（带 keyword）', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => wrap({ list: [] }) }))
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpDictRemoteSource({ endpoint: '/api/mdm/v1', headers: {} })

    await source.searchUsers?.({ keyword: '张', pageSize: 20 })
    const url = String((fetchMock.mock.calls[0] as unknown as [string])[0])
    expect(url).toContain('/api/mdm/v1/data-source/users?')
    expect(url).toContain('keyword=%E5%BC%A0')
    expect(url).toContain('size=20')
  })

  it('验证码：出题 / 短信 / 校验 / 场景策略四端点', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => wrap({ ok: true }) }))
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpCaptchaSource({ endpoint: '/api/identity/v1', headers: {} })

    await source.challenge?.({ scene: 'login', kind: 'image' })
    await source.sendSms?.({ scene: 'login', phone: '13800000000' })
    await source.verify?.({ captchaId: 'c1', kind: 'image', code: '1234', scene: 'login' })
    await source.policy?.({ scene: 'login' })

    const urls = fetchMock.mock.calls.map((call) => String((call as unknown as [string])[0]))
    expect(urls[0]).toContain('/api/identity/v1/captcha/challenges')
    expect(urls[1]).toContain('/api/identity/v1/captcha/sms')
    expect(urls[2]).toContain('/api/identity/v1/captcha/verify')
    expect(urls[3]).toContain('/api/identity/v1/captcha/scenes/login/policy')
  })
})
