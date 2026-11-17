// kiwi_id: 2525
/** 帮助 HTTP 取数（09_02）：路径 / 线参数 / 解包 / 失败文案。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { createHttpHelpFetcher } from '../src'

/** 统一响应包装。 */
function wrap(data: unknown): unknown {
  return { code: 0, message: '', data }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createHttpHelpFetcher（09_02）', () => {
  it('GET /help/context 携带 snake_case 参数并解包', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => wrap({ matched: true, anchor_found: true, level: 'module' }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const fetcher = createHttpHelpFetcher({ endpoint: '/api/platform/v1', headers: { Authorization: 'Bearer t' } })

    const raw = await fetcher({ module_key: 'system', form_key: 'user', action_code: '' })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/platform/v1/help/context?module_key=system&form_key=user')
    expect(init.method).toBe('GET')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer t')
    expect(raw).toMatchObject({ matched: true, anchor_found: true })
  })

  it('无参数时不带查询串；业务码非 0 抛后端文案', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ code: 10001, message: '参数非法', data: null }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const fetcher = createHttpHelpFetcher({ endpoint: '/api/v1' })
    await expect(fetcher({})).rejects.toThrow('参数非法')
    expect(String((fetchMock.mock.calls[0] as unknown as [string])[0])).toBe('/api/v1/help/context')
  })

  it('HTTP 失败与无 fetch 能力均抛「帮助服务不可用」', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({}) })))
    const fetcher = createHttpHelpFetcher()
    await expect(fetcher({})).rejects.toThrow('帮助服务不可用')

    vi.stubGlobal('fetch', undefined)
    await expect(fetcher({})).rejects.toThrow('帮助服务不可用')
  })
})
