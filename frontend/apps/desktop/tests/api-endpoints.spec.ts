/** 能力源端点解析用例（04-1-1 / Kiwi 2191）：按服务注入 endpoint 与令牌头。 */
// kiwi_id: 2191

import { afterEach, describe, expect, it } from 'vitest'

import {
  aiStreamEndpoint,
  authHeaders,
  captchaSourceOptions,
  dictSourceOptions,
  orgSourceOptions,
  searchEngineOptions,
  sourceEndpoint,
  uploadTransportOptions,
} from '@/api/endpoints'
import { setAccessToken } from '@/api/token'

afterEach(() => {
  setAccessToken(null)
})

describe('能力源端点按服务分流（Kiwi 2191）', () => {
  it('各能力源 endpoint 指向对应服务', () => {
    expect(dictSourceOptions().endpoint).toBe('/api/platform/v1')
    expect(orgSourceOptions().endpoint).toBe('/api/org/v1')
    expect(captchaSourceOptions().endpoint).toBe('/api/identity/v1')
    expect(uploadTransportOptions().endpoint).toBe('/api/file/v1')
    expect(searchEngineOptions().endpoint).toBe('/api/search/v1')
    expect(sourceEndpoint('notification').endpoint).toBe('/api/notification/v1')
  })

  it('AI 流式端点指向 ai 服务', () => {
    expect(aiStreamEndpoint()).toBe('/api/ai/v1/chat/stream')
    expect(aiStreamEndpoint('/chat')).toBe('/api/ai/v1/chat')
  })

  it('authHeaders 有 / 无令牌两态', () => {
    expect(authHeaders()).toEqual({})
    setAccessToken('t1')
    expect(authHeaders()).toEqual({ Authorization: 'Bearer t1' })
  })

  it('端点选项的 headers 动态取令牌', () => {
    const options = dictSourceOptions()
    expect(options.headers()).toEqual({})
    setAccessToken('t2')
    expect(options.headers()).toEqual({ Authorization: 'Bearer t2' })
  })
})
