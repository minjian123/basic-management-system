// kiwi_id: 977
/** 模块文案承载用例（并入 / 还原 / 取文案；不跨来源合并、未命中不兜底）。 */

import { describe, expect, it } from 'vitest'

import { ModuleMessageStore } from '../src'

describe('ModuleMessageStore（Kiwi 977）', () => {
  it('并入文案包：语言标识自键派生并小写归一', () => {
    const store = new ModuleMessageStore('zh-cn')
    const keys = store.merge([
      { key: 'demo:zh-cn', messages: { 'demo.title': '演示模块' } },
      { key: 'demo:EN', messages: { 'demo.title': 'Demo module' } },
    ])

    expect(keys).toEqual(['demo:zh-cn', 'demo:EN'])
    expect(store.size).toBe(2)
    expect(store.locales()).toEqual(['zh-cn', 'en'])
    expect(store.keys()).toEqual(['demo:zh-cn', 'demo:EN'])
  })

  it('取文案：缺省语言命中，未命中返回 undefined', () => {
    const store = new ModuleMessageStore('zh-cn')
    store.merge([
      { key: 'demo:zh-cn', messages: { 'demo.title': '演示模块' } },
      { key: 'demo:en', messages: { 'demo.title': 'Demo module' } },
    ])

    expect(store.translate('demo.title')).toBe('演示模块')
    expect(store.translate('demo.title', 'EN')).toBe('Demo module')
    expect(store.translate('missing.key')).toBeUndefined()
    expect(store.translate('demo.title', 'ja')).toBeUndefined()
  })

  it('合并视图按并入序（后者覆盖同名键），不跨来源兜底', () => {
    const store = new ModuleMessageStore()
    store.merge([
      { key: 'demo:zh-cn', messages: { 'common.ok': '确定', 'demo.title': '演示模块' } },
      { key: 'biz:zh-cn', messages: { 'common.ok': '好的' } },
    ])

    expect(store.messagesOf('ZH-CN')).toEqual({ 'common.ok': '好的', 'demo.title': '演示模块' })
    expect(store.messagesOf('ja')).toEqual({})
  })

  it('还原按键逆序移除且幂等（重复并入同键即替换）', () => {
    const store = new ModuleMessageStore()
    const first = store.merge([{ key: 'demo:zh-cn', messages: { 'demo.title': '演示模块' } }])
    store.merge([{ key: 'demo:zh-cn', messages: { 'demo.title': '演示模块（改）' } }])

    expect(store.size).toBe(1)
    expect(store.translate('demo.title')).toBe('演示模块（改）')

    store.restore(first)
    store.restore(first)
    expect(store.size).toBe(0)
    expect(store.translate('demo.title')).toBeUndefined()
    expect(store.locales()).toEqual([])
  })
})
