/** Axios 基线用例（Kiwi 25）：request 解包/错误、fetchAppInfo、请求与响应拦截器分支。 */

import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { appInfoClient, fetchAppInfo, http, request } from '@/api/http'

function asResponse<T>(data: T): AxiosResponse<T> {
  return { data } as unknown as AxiosResponse<T>
}

interface InterceptorHandlers {
  fulfilled?: (value: never) => unknown
  rejected?: (error: unknown) => unknown
}

function responseHandlers(): InterceptorHandlers[] {
  return (http.interceptors.response as unknown as { handlers: InterceptorHandlers[] }).handlers
}

function requestHandlers(): InterceptorHandlers[] {
  return (http.interceptors.request as unknown as { handlers: InterceptorHandlers[] }).handlers
}

describe('Axios 基线（Kiwi 25）', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('request：code=0 解包 data', async () => {
    vi.spyOn(http, 'request').mockResolvedValue(asResponse({ code: 0, message: 'ok', data: { id: '1' } }))
    expect(await request({ url: '/x' })).toEqual({ id: '1' })
  })

  it('request：code≠0 拒绝（message 与兜底文案）', async () => {
    vi.spyOn(http, 'request').mockResolvedValueOnce(asResponse({ code: 500, message: '业务失败', data: null }))
    await expect(request({ url: '/x' })).rejects.toThrow('业务失败')

    vi.spyOn(http, 'request').mockResolvedValueOnce(asResponse({ code: 500, message: '', data: null }))
    await expect(request({ url: '/x' })).rejects.toThrow('业务错误 500')
  })

  it('fetchAppInfo：解析 /info 应用信息', async () => {
    vi.spyOn(appInfoClient, 'get').mockResolvedValue(
      asResponse({ code: 0, message: 'ok', data: { name: 'BMS 基础管理系统', version: '0.1.0' } }),
    )
    expect(await fetchAppInfo()).toEqual({ name: 'BMS 基础管理系统', version: '0.1.0' })
  })

  it('请求拦截器：透传 config', () => {
    const config = { url: '/x' }
    expect(requestHandlers()[0]?.fulfilled?.(config as never)).toBe(config)
  })

  it('响应拦截器：成功透传响应', () => {
    const response = asResponse({ code: 0, message: 'ok', data: null })
    expect(responseHandlers()[0]?.fulfilled?.(response as never)).toBe(response)
  })

  it('响应拦截器：401 与普通错误均透传', async () => {
    const unauthorized = new AxiosError('unauthorized', 'ERR_BAD_REQUEST', undefined, undefined, {
      status: 401,
    } as AxiosResponse)
    const serverError = new AxiosError('server', 'ERR_BAD_RESPONSE', undefined, undefined, {
      status: 500,
    } as AxiosResponse)
    const plain = new Error('network')

    for (const error of [unauthorized, serverError, plain]) {
      const result = responseHandlers()[0]?.rejected?.(error) as Promise<never>
      await expect(result).rejects.toBe(error)
    }
  })
})
