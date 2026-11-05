/** 能力源端点解析用例（04-1-1 / Kiwi 2191）：按服务注入 endpoint 与令牌头。 */
// kiwi_id: 2191
// kiwi_id: 2363

import { afterEach, describe, expect, it } from 'vitest'

import { applyCatalogSnapshot, resetCatalog } from '@bms/core'
import { DICT_SOURCE_DOMAIN } from '@bms/ui_ep'

import {
  aiStreamEndpoint,
  authHeaders,
  captchaSourceOptions,
  dictSourceOptions,
  dictRemoteSourceOptions,
  searchEngineOptions,
  sourceEndpoint,
  uploadTransportOptions,
} from '@/api/endpoints'
import { setAccessToken } from '@/api/token'

/** 组织数据源目录夹具（虚构产品 `demo`：一个数据源类能力 + 平台服务行）。 */
const DICT_DATA_CATALOG = {
  products: [{ productKey: 'demo', status: 'enabled' }],
  services: [
    { serviceKey: 'platform', serviceGroup: 'foundation', status: 'enabled' },
    { serviceKey: 'identity', serviceGroup: 'foundation', status: 'enabled' },
    { serviceKey: 'file', serviceGroup: 'capability', status: 'enabled' },
    { serviceKey: 'search', serviceGroup: 'capability', status: 'enabled' },
    { serviceKey: 'notification', serviceGroup: 'capability', status: 'enabled' },
  ],
  collaborations: [
    { name: 'demo.org.dept-data', domain: DICT_SOURCE_DOMAIN, kind: 'dataset', productKey: 'demo', frontendPrefix: 'demo' },
  ],
  warnings: [],
}

afterEach(() => {
  setAccessToken(null)
  resetCatalog()
})

describe('能力源端点按服务分流（Kiwi 2191）', () => {
  it('各能力源 endpoint 指向对应服务', () => {
    applyCatalogSnapshot(DICT_DATA_CATALOG)
    expect(dictSourceOptions().endpoint).toBe('/api/platform/v1')
    expect(dictRemoteSourceOptions().endpoint).toBe('/api/demo/v1/demo')
    expect(captchaSourceOptions().endpoint).toBe('/api/identity/v1')
    expect(uploadTransportOptions().endpoint).toBe('/api/file/v1')
    expect(searchEngineOptions().endpoint).toBe('/api/search/v1')
    expect(sourceEndpoint('notification').endpoint).toBe('/api/notification/v1')
  })

  it('组织数据源端点按目录取址：目录不可用时不给端点（消费方降级、不发起请求）', () => {
    expect(dictRemoteSourceOptions().endpoint).toBeUndefined()
    applyCatalogSnapshot({ ...DICT_DATA_CATALOG, collaborations: [] })
    expect(dictRemoteSourceOptions().endpoint).toBeUndefined()
    resetCatalog()
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
