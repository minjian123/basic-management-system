// kiwi_id: 964
/** 字典缓存能力基类用例（06_06）：契约同实现（核心 + 投影）+ 身份依赖 + 本地二次缓存 + 失效。 */

import { describe, expect, it } from 'vitest'

import { BaseComponent, BaseDictStore, BasePlaceholderState, bindDictStoreSource } from '@bms/core'
import { createDictSourceStub, describeDictStoreContract, type DictStoreContractTarget } from '@bms/core/testing'

/** 具体字典缓存（可实例化）。 */
class DictStoreState extends BaseDictStore {}

/**
 * 把缓存基类适配为契约目标（投影层同构适配）。
 *
 * @returns 契约目标。
 */
function makeTarget(): DictStoreContractTarget {
  const store = new DictStoreState()
  return {
    get ready() {
      return store.ready
    },
    get degraded() {
      return store.degraded
    },
    get requestCount() {
      return store.requestCount
    },
    get loadedTypes() {
      return store.loadedTypes
    },
    get largeTypes() {
      return store.largeTypes
    },
    get cacheSize() {
      return store.cacheSize
    },
    get subsetSize() {
      return store.subsetSize
    },
    setReady: (value) => store.setReady(value),
    setSource: (source) => bindDictStoreSource(store, source),
    setStorage: (channel) =>
      store.setStorage(
        channel as { read(key: string): string | undefined; write(key: string, value: string): void; remove(key: string): void },
      ),
    setLocale: (locale) => store.setLocale(locale),
    ensureTypes: (types) => store.ensureTypes(types),
    ensureType: (dictType) => store.ensureType(dictType),
    searchRemote: (dictType, keyword) => store.searchRemote(dictType, keyword),
    resolveValues: (dictType, values) => store.resolveValues(dictType, values),
    itemsOf: (dictType) => store.itemsOf(dictType),
    labelOf: (dictType, value) => store.labelOf(dictType, value),
    isLoaded: (dictType) => store.isLoaded(dictType),
    isLarge: (dictType) => store.isLarge(dictType),
    invalidate: (dictType) => store.invalidate(dictType),
  }
}

describeDictStoreContract('字典缓存契约（BaseDictStore）', makeTarget)

describe('BaseDictStore 继承链与身份', () => {
  it('身份与依赖登记', () => {
    const store = new DictStoreState()
    expect(store).toBeInstanceOf(BasePlaceholderState)
    expect(store).toBeInstanceOf(BaseComponent)
    expect(store.identifier).toBe('dict-store')
    expect(store.depends).toEqual(['placeholder-state'])
  })

  it('切换语言清空缓存', async () => {
    const store = new DictStoreState()
    const stub = createDictSourceStub()
    store.setReady(true)
    bindDictStoreSource(store, stub.source)
    await store.ensureType('user_status')
    expect(store.isLoaded('user_status')).toBe(true)
    store.setLocale('en-US')
    expect(store.cacheSize).toBe(0)
    expect(store.subsetSize).toBe(0)
  })

  it('远程搜索不写类型缓存', async () => {
    const store = new DictStoreState()
    const stub = createDictSourceStub()
    store.setReady(true)
    bindDictStoreSource(store, stub.source)
    const candidates = await store.searchRemote('user_status', '启')
    expect(candidates.map((item) => item.value)).toEqual(['enabled'])
    expect(store.isLoaded('user_status')).toBe(false)
  })

  it('释放后不再广播（安全）', () => {
    const store = new DictStoreState()
    store.dispose()
    store.setSource(createDictSourceStub().source)
    expect(store.isDisposed).toBe(true)
  })
})
