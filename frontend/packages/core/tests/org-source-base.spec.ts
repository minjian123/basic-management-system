// kiwi_id: 2363
/**
 * 组织数据源插件基类与注册表契约用例（06_05 / 07B 03_02）：
 * 基类默认实现（未覆写即不请求）、注册项工厂字段、注册表同键拒重。
 */

import { describe, expect, it } from 'vitest'

import { BaseOrgSource, OrgSourceProvider, OrgSourceRegistry } from '../src'

/** 基类探针实现（不覆写任何方法，验证默认契约）。 */
class ProbeOrgSource extends BaseOrgSource {}

describe('组织数据源基类默认实现（06_05）', () => {
  it('未覆写的方法一律返回 undefined（不请求）', async () => {
    const source = new ProbeOrgSource()

    expect(source.pluginKey).toBe('org-source')
    expect(source.pluginName).toBe('base')
    await expect(source.searchUsers({})).resolves.toBeUndefined()
    await expect(source.searchPosts({})).resolves.toBeUndefined()
    await expect(source.loadDeptTree({})).resolves.toBeUndefined()
    await expect(source.resolveNames({ target: 'user', ids: ['u1'] })).resolves.toBeUndefined()
  })
})

describe('组织数据源注册表（06_05）', () => {
  it('登记与按键取用；同键重复登记抛错', () => {
    const source = new ProbeOrgSource()
    const provider = new OrgSourceProvider('probe', () => source)
    const registry = new OrgSourceRegistry()

    expect(provider.key).toBe('probe')
    expect(provider.create({ endpoint: '/api/demo/v1/demo' })).toBe(source)

    registry.register(provider)
    expect(registry.get('probe')).toBe(provider)
    expect(() => registry.register(new OrgSourceProvider('probe', () => source))).toThrow()
  })
})
