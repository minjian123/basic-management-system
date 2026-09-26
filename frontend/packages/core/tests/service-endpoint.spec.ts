/** 服务寻址契约用例（04-1-1 / Kiwi 2191）：服务键 / 服务前缀 / URL 组装与边界。 */
// kiwi_id: 2191

import { describe, expect, it } from 'vitest'

import { BaseError, SERVICE_KEYS, isServiceKey, servicePrefix, serviceUrl } from '../src'

describe('服务键与「域 → 服务前缀」映射（Kiwi 2191）', () => {
  it('服务键为 9 个已启用服务且顺序与目录一致', () => {
    expect(SERVICE_KEYS).toEqual([
      'platform',
      'identity',
      'tenant',
      'org',
      'file',
      'notification',
      'search',
      'ai',
      'report',
    ])
  })

  it('isServiceKey 正反例', () => {
    expect(isServiceKey('platform')).toBe(true)
    expect(isServiceKey('workflow')).toBe(false)
    expect(isServiceKey(1)).toBe(false)
    expect(isServiceKey(undefined)).toBe(false)
  })

  it('servicePrefix 逐服务给出外部前缀', () => {
    for (const service of SERVICE_KEYS) {
      expect(servicePrefix(service)).toBe(`/api/${service}/v1`)
    }
  })

  it('未登记服务键抛参数段位错误', () => {
    try {
      servicePrefix('workflow' as never)
      throw new Error('should throw')
    } catch (error) {
      expect(error).toBeInstanceOf(BaseError)
      expect((error as BaseError).code).toBe(10001)
    }
  })
})

describe('serviceUrl 组装与路径归一（Kiwi 2191）', () => {
  it('空路径返回前缀本身', () => {
    expect(serviceUrl('platform')).toBe('/api/platform/v1')
    expect(serviceUrl('platform', '')).toBe('/api/platform/v1')
  })

  it('带 / 与不带 / 的首部斜杠等价', () => {
    expect(serviceUrl('org', '/users')).toBe('/api/org/v1/users')
    expect(serviceUrl('org', 'users')).toBe('/api/org/v1/users')
  })

  it('折叠重复斜杠', () => {
    expect(serviceUrl('file', '//files//uploads')).toBe('/api/file/v1/files/uploads')
  })

  it('保留查询串与深层路径', () => {
    expect(serviceUrl('search', '/search/global?q=a&page=1')).toBe('/api/search/v1/search/global?q=a&page=1')
  })
})
