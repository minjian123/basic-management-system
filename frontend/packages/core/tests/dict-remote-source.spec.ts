// kiwi_id: 2363
/**
 * 字典数据源插件基类与注册表契约用例（06_05 / 07B 03_02）：
 * 基类默认实现（未覆写即不请求）、注册项工厂字段、注册表同键拒重。
 */

import { describe, expect, it } from 'vitest'

import { BaseDictRemoteSource, DictRemoteSourceProvider, DictRemoteSourceRegistry } from '../src'

/** 基类探针实现（不覆写任何方法，验证默认契约）。 */
class ProbeDictRemoteSource extends BaseDictRemoteSource {}

describe('字典数据源基类默认实现（06_05）', () => {
  it('未覆写的方法一律返回 undefined（不请求）', async () => {
    const source = new ProbeDictRemoteSource()

    expect(source.pluginKey).toBe('dict-remote-source')
    expect(source.pluginName).toBe('base')
    await expect(source.searchUsers({})).resolves.toBeUndefined()
    await expect(source.searchPosts({})).resolves.toBeUndefined()
    await expect(source.loadDeptTree({})).resolves.toBeUndefined()
    await expect(source.resolveNames({ target: 'user', ids: ['u1'] })).resolves.toBeUndefined()
  })
})

describe('字典数据源注册表（06_05）', () => {
  it('登记与按键取用；同键重复登记抛错', () => {
    const source = new ProbeDictRemoteSource()
    const provider = new DictRemoteSourceProvider('probe', () => source)
    const registry = new DictRemoteSourceRegistry()

    expect(provider.key).toBe('probe')
    expect(provider.create({ endpoint: '/api/demo/v1/demo' })).toBe(source)

    registry.register(provider)
    expect(registry.get('probe')).toBe(provider)
    expect(() => registry.register(new DictRemoteSourceProvider('probe', () => source))).toThrow()
  })
})
