/** 请求层用例：统一响应解包 / 错误 / 令牌 / 请求入口。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { afterEach, describe, expect, it } from 'vitest'

import { ApiError, SessionExpiredError } from '@/api/error'
import { del, get, newKey, post, put } from '@/api/request'
import { unwrap, unwrapPage } from '@/api/response'
import { getAccessToken, setAccessToken } from '@/api/token'

afterEach(() => {
  setAccessToken(null)
  configureRequestAdapter({ request: async () => undefined })
})

describe('统一响应解包', () => {
  it('成功解包 data；分页解包', () => {
    expect(unwrap({ code: 0, message: 'ok', data: { id: 1 } })).toEqual({ id: 1 })
    expect(unwrapPage({ code: 0, message: 'ok', data: { list: [1], total: 1, page: 1, size: 20 } }).total).toBe(1)
  })

  it('业务码非 0 抛 ApiError', () => {
    try {
      unwrap({ code: 10003, message: '冲突', data: null })
      throw new Error('should throw')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).code).toBe(10003)
    }
  })

  it('会话失效错误继承 ApiError', () => {
    expect(new SessionExpiredError()).toBeInstanceOf(ApiError)
  })
})

describe('令牌内存存储', () => {
  it('设置 / 读取 / 清除', () => {
    setAccessToken('t1')
    expect(getAccessToken()).toBe('t1')
    setAccessToken(null)
    expect(getAccessToken()).toBeNull()
  })
})

describe('请求入口', () => {
  it('拼前缀、方法、写方法带幂等键', async () => {
    const calls: RequestConfig[] = []
    configureRequestAdapter({
      request: async <T,>(config: RequestConfig): Promise<T> => {
        calls.push(config)
        return undefined as T
      },
    })
    await get('/a', { q: 1 })
    await post('/b', { x: 1 })
    await put('/c')
    await del('/d', { id: 1 })

    expect(calls[0]).toMatchObject({ method: 'GET', url: '/api/v1/a', params: { q: 1 } })
    expect(calls[1]?.method).toBe('POST')
    expect(calls[1]?.idempotencyKey).toBeTruthy()
    expect(calls[2]?.method).toBe('PUT')
    expect(calls[3]).toMatchObject({ method: 'DELETE', url: '/api/v1/d' })
  })

  it('幂等键含前缀且唯一', () => {
    expect(newKey('x')).toContain('x:')
    expect(newKey()).not.toBe(newKey())
  })
})
