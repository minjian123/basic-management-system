/** 请求适配契约用例（02-6）。 */

import { describe, expect, it } from 'vitest'

import {
  BaseError,
  configureRequestAdapter,
  getRequestAdapter,
  request,
  type RequestAdapter,
  type RequestConfig,
} from '../src'

describe('请求适配契约', () => {
  it('未注入适配器：占位抛 BaseError(19001)，不请求', async () => {
    expect(getRequestAdapter()).toBeUndefined()
    try {
      await request({ method: 'GET', url: '/api/v1/demo' })
      throw new Error('should throw')
    } catch (error) {
      expect(error).toBeInstanceOf(BaseError)
      expect((error as BaseError).code).toBe(19001)
    }
  })

  it('注入适配器：按配置调用并返回业务数据', async () => {
    const calls: RequestConfig[] = []
    const adapter: RequestAdapter = {
      request: async <T,>(config: RequestConfig): Promise<T> => {
        calls.push(config)
        return { ok: true } as T
      },
    }
    configureRequestAdapter(adapter)
    const result = await request<{ ok: boolean }>({
      method: 'POST',
      url: '/api/v1/demo',
      idempotencyKey: 'k1',
    })
    expect(result).toEqual({ ok: true })
    expect(calls).toEqual([{ method: 'POST', url: '/api/v1/demo', idempotencyKey: 'k1' }])
    expect(getRequestAdapter()).toBe(adapter)
  })
})
