// kiwi_id: 964, 2331
/** 字典选择族 / 高级查询编排用例（06_06）：契约同实现（核心 + 投影）+ 身份依赖 + 选项源语义。 */

import {
  BaseComponent,
  BaseDictQuery,
  BaseDictSelect,
  BaseDictStore,
  BaseField,
  BaseOptionSource,
  BasePlaceholderState,
  bindDictStoreSource,
} from '@bms/core'
import {
  createDictSourceStub,
  describeDictQueryContract,
  describeDictSelectContract,
  type DictQueryContractTarget,
  type DictSelectContractTarget,
} from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

/** 具体字典选择族（可实例化）。 */
class DictSelectState extends BaseDictSelect {}

/** 具体字典缓存（可实例化）。 */
class DictStoreState extends BaseDictStore {}

/** 具体高级查询编排（可实例化）。 */
class DictQueryState extends BaseDictQuery {}

/**
 * 把选择族适配为契约目标。
 *
 * @returns 契约目标。
 */
function makeSelectTarget(): DictSelectContractTarget {
  const select = new DictSelectState()
  const store = new DictStoreState()
  select.setStore(store)
  return {
    get ready() {
      return select.ready
    },
    get degraded() {
      return select.degraded
    },
    get requestCount() {
      return select.requestCount
    },
    get dataSourceKey() {
      return select.dataSourceKey
    },
    get items() {
      return select.items
    },
    get selectedValues() {
      return select.selectedValues
    },
    get isLarge() {
      return select.isLarge
    },
    get limitExceeded() {
      return select.limitExceeded
    },
    get dataVersion() {
      return select.dataVersion
    },
    setReady: (value) => {
      select.setReady(value)
      store.setReady(value)
    },
    setSource: (source) => {
      select.setSource(source)
      bindDictStoreSource(store, source)
    },
    setStore: () => undefined,
    setDictType: (dataSourceKey) => select.setDictType(dataSourceKey),
    setKeyword: (keyword) => select.setKeyword(keyword),
    setParent: (parentId) => select.setParent(parentId),
    setMultiple: (value) => select.setMultiple(value),
    setLimit: (limit) => select.setLimit(limit),
    setValue: (value) => select.setValue(value),
    toggle: (value) => select.toggle(value),
    remove: (value) => select.remove(value),
    clearSelection: () => select.clearSelection(),
    load: () => select.load(),
    searchRemote: (keyword) => select.searchRemote(keyword),
    resolve: (extra) => select.resolve(extra),
    invalidate: () => select.invalidate(),
    labelOf: (id) => select.labelOf(id),
    selectionText: () => select.selectionText(),
    limitText: () => select.limitText(),
    getLabel: (value) => select.getLabel(value),
    searchLocal: (keyword) => select.search(keyword).map((item) => ({ value: String(item.value), label: item.label })),
  }
}

describeDictSelectContract('字典选择契约（BaseDictSelect）', makeSelectTarget)

describe('BaseDictSelect 继承链与身份', () => {
  it('身份与依赖登记（选项源语义入值链）', () => {
    const select = new DictSelectState()
    expect(select).toBeInstanceOf(BaseOptionSource)
    expect(select).toBeInstanceOf(BaseField)
    expect(select.identifier).toBe('dict_select')
    expect(select.depends).toEqual(['option_source', 'dict_store'])
  })
})

/**
 * 把高级查询编排适配为契约目标。
 *
 * @returns 契约目标。
 */
function makeQueryTarget(): DictQueryContractTarget {
  const query = new DictQueryState()
  return {
    get ready() {
      return query.ready
    },
    get degraded() {
      return query.degraded
    },
    get requestCount() {
      return query.requestCount
    },
    get target() {
      return query.target
    },
    get attrs() {
      return query.attrs
    },
    get providers() {
      return query.providers
    },
    get conditions() {
      return query.conditions
    },
    get results() {
      return query.results
    },
    get rows() {
      return query.rows
    },
    get total() {
      return query.total
    },
    get errorMessage() {
      return query.errorMessage
    },
    get schemes() {
      return query.schemes
    },
    get fieldOptions() {
      return query.fieldOptions
    },
    setReady: (value) => query.setReady(value),
    setSource: (source) => query.setSource(source),
    setDictType: (dataSourceKey) => query.setDictType(dataSourceKey),
    setTarget: (target) => query.setTarget(target === 'business' ? 'business' : 'items'),
    setConditions: (group) => query.setConditions(group),
    setProvider: (key, params) => query.setProvider(key, params),
    setPage: (page) => query.setPage(page),
    loadMeta: () => query.loadMeta(),
    run: () => query.run(),
    reset: () => query.reset(),
    loadSchemes: () => query.loadSchemes(),
    resolveDefaultScheme: () => query.resolveDefaultScheme(),
    applyScheme: (scheme) => query.applyScheme(scheme),
    saveScheme: (name) => query.saveScheme(name),
    deleteScheme: (schemeId) => query.deleteScheme(schemeId),
    toBusinessFilter: () => query.toBusinessFilter(),
    selectedIds: () => query.selectedIds(),
  }
}

describeDictQueryContract('字典高级查询契约（BaseDictQuery）', makeQueryTarget)

describe('BaseDictSelect 未命中回显（06_09）', () => {
  it('回填未命中记入 missingIds 并以原 id 占位；候选出现后清除', async () => {
    const stub = createDictSourceStub()
    const store = new DictStoreState()
    store.setReady(true)
    bindDictStoreSource(store, stub.source)
    const select = new DictSelectState()
    select.setReady(true)
    select.setStore(store)
    select.setDictType('user_status')
    select.setMultiple(true)

    select.setValue(['101', 'ghost'])
    await select.resolve()
    expect(select.missingIds).toEqual(['ghost'])
    expect(select.labelOf('ghost')).toBe('ghost')
    expect(select.getLabel(['101', 'ghost'])).toBe('启用、ghost')

    // 二次回显不重复请求
    const before = store.requestCount
    await select.resolve()
    expect(store.requestCount).toBe(before)

    // 候选命中后从未命中集合移除（接口返回真实条目）
    stub.largeTypes.add('user_status')
    select.setKeyword('停')
    await select.load()
    expect(select.missingIds).toEqual([])
  })

  it('切换类型与失效清空未命中集合', async () => {
    const stub = createDictSourceStub()
    const store = new DictStoreState()
    store.setReady(true)
    bindDictStoreSource(store, stub.source)
    const select = new DictSelectState()
    select.setReady(true)
    select.setStore(store)
    select.setDictType('user_status')

    select.setValue(['ghost'])
    await select.resolve()
    expect(select.missingIds).toEqual(['ghost'])
    select.setDictType('biz_type')
    expect(select.missingIds).toEqual([])

    select.setValue(['ghost'])
    await select.resolve()
    expect(select.missingIds).toEqual(['ghost'])
    select.invalidate()
    expect(select.missingIds).toEqual([])
  })

  it('未注入缓存时经数据源按 ids 回填并记录未命中', async () => {
    const stub = createDictSourceStub()
    const select = new DictSelectState()
    select.setReady(true)
    select.setSource(stub.source)
    select.setDictType('user_status')
    select.setMultiple(true)

    select.setValue(['101', 'ghost'])
    await select.resolve()
    expect(stub.queries.at(-1)?.ids).toEqual(['101', 'ghost'])
    expect(select.labelOf('101')).toBe('启用')
    expect(select.missingIds).toEqual(['ghost'])
  })
})

describe('BaseDictQuery 继承链与身份', () => {
  it('身份与依赖登记', () => {
    const query = new DictQueryState()
    expect(query).toBeInstanceOf(BasePlaceholderState)
    expect(query).toBeInstanceOf(BaseComponent)
    expect(query.identifier).toBe('dict_query')
    expect(query.depends).toEqual(['placeholder_state', 'dict_store'])
  })

  it('字段项包含固定字段与属性', async () => {
    const query = new DictQueryState()
    const stub = createDictSourceStub()
    query.setReady(true)
    query.setSource(stub.source)
    query.setDictType('region')
    await query.loadMeta()
    expect(query.fieldOptions.map((field) => field.field)).toEqual(
      expect.arrayContaining(['value', 'label', 'code', 'sort', 'status', 'attr.level']),
    )
  })
})
