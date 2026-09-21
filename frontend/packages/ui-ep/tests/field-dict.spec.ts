// kiwi_id: 964
/** 字典字段用例（06_06）：契约套件（核心 + 投影）+ 五件 + 工具（HTTP 数据源 / 本地通道 / 翻译器）+ 占位契约复用。 */

import { BaseDictStore, DICT_SEARCH_DEBOUNCE, bindDictStoreSource } from '@bms/core'
import {
  createDictSourceStub,
  describeDictQueryContract,
  describeDictSelectContract,
  describeDictStoreContract,
  describePlaceholderFieldContract,
  type DictQueryContractTarget,
  type DictSelectContractTarget,
  type DictStoreContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { effectScope, defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ConditionGroupBuilder,
  DictAdvancedQuery,
  DictCascaderField,
  DictLabel,
  DictSelectField,
  createDictTranslator,
  createHttpDictSource,
  dictSourceRegistry,
  localStorageDictChannel,
  registerDictSource,
  useBaseDictQuery,
  useBaseDictSelect,
  type UseBaseDictQueryResult,
  type UseBaseDictSelectResult,
} from '../src'

const ElSelectStub = {
  name: 'ElSelect',
  props: {
    modelValue: { type: [String, Number, Array], default: undefined },
    multiple: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    remote: { type: Boolean, default: false },
    remoteMethod: { type: Function, default: undefined },
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    clearable: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    collapseTags: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'visible-change'],
  template: '<div class="el-select-stub"><slot /><slot name="empty" /></div>',
}

const ElSelectV2Stub = {
  name: 'ElSelectV2',
  props: {
    modelValue: { type: [String, Number, Array], default: undefined },
    options: { type: Array, default: () => [] },
    multiple: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    remote: { type: Boolean, default: false },
    remoteMethod: { type: Function, default: undefined },
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'visible-change'],
  template: '<div class="el-select-v2-stub"><slot /><slot name="empty" /></div>',
}

const ElOptionStub = {
  name: 'ElOption',
  props: {
    label: { type: String, default: '' },
    value: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
  },
  template: '<div class="el-option-stub"><slot /></div>',
}

const ElInputStub = {
  name: 'ElInput',
  props: {
    modelValue: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<input class="el-input-stub" />',
}

const ElButtonStub = defineComponent({
  name: 'ElButton',
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
})

const ElDrawerStub = {
  name: 'ElDrawer',
  props: {
    modelValue: { type: Boolean, default: false },
    title: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-drawer-stub"><slot /></div>',
}

const ElCascaderStub = {
  name: 'ElCascader',
  props: {
    modelValue: { type: [Array], default: undefined },
    options: { type: Array, default: () => [] },
    multiple: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'change'],
  template: '<div class="el-cascader-stub"></div>',
}

const stubs = {
  ElSelect: ElSelectStub,
  ElSelectV2: ElSelectV2Stub,
  ElOption: ElOptionStub,
  ElInput: ElInputStub,
  ElButton: ElButtonStub,
  ElDrawer: ElDrawerStub,
  ElCascader: ElCascaderStub,
  ConditionGroupBuilder: true,
}

/** 契约目标（投影适配）。 */
function makeStoreTarget(): DictStoreContractTarget {
  const api = effectScope(true).run(() => useBaseDictSelect({ storage: undefined })) as UseBaseDictSelectResult
  const store = api.store
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
    setStorage: (channel) => store.setStorage(channel as never),
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

function makeSelectTarget(): DictSelectContractTarget {
  const api = effectScope(true).run(() => useBaseDictSelect({ storage: undefined })) as UseBaseDictSelectResult
  const select = api.select
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
    get dictType() {
      return select.dictType
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
    setReady: (value) => api.setReady(value),
    setSource: (source) => api.setSource(source),
    setStore: () => undefined,
    setDictType: (dictType) => api.setDictType(dictType),
    setKeyword: (keyword) => api.setKeyword(keyword),
    setParent: (parentId) => api.setParent(parentId),
    setMultiple: (value) => api.setMultiple(value),
    setLimit: (limit) => api.setLimit(limit),
    setValue: (value) => api.setValue(value),
    toggle: (value) => api.toggle(value),
    remove: (value) => api.remove(value),
    clearSelection: () => api.clearSelection(),
    load: () => api.load(),
    searchRemote: (keyword) => api.searchRemote(keyword),
    resolve: (extra) => api.resolve(extra),
    invalidate: () => api.invalidate(),
    labelOf: (value) => api.labelOf(value),
    selectionText: () => api.selectionText(),
    limitText: () => api.limitText.value,
    getLabel: (value) => api.getLabel(value),
    searchLocal: (keyword) => select.search(keyword).map((item) => ({ value: String(item.value), label: item.label })),
  }
}

function makeQueryTarget(): DictQueryContractTarget {
  const api = effectScope(true).run(() => useBaseDictQuery()) as UseBaseDictQueryResult
  const query = api.query
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
    setReady: (value) => api.setReady(value),
    setSource: (source) => api.setSource(source),
    setDictType: (dictType) => api.setDictType(dictType),
    setTarget: (target) => api.setTarget(target === 'business' ? 'business' : 'items'),
    setConditions: (group) => api.setConditions(group),
    setProvider: (key, params) => api.setProvider(key, params),
    setPage: (page) => api.setPage(page),
    loadMeta: () => api.loadMeta(),
    run: () => api.run(),
    reset: () => api.reset(),
    loadSchemes: () => api.loadSchemes(),
    resolveDefaultScheme: () => api.resolveDefaultScheme(),
    applyScheme: (scheme) => api.applyScheme(scheme),
    saveScheme: (name) => api.saveScheme(name),
    deleteScheme: (schemeId) => api.deleteScheme(schemeId),
    toBusinessFilter: () => api.toBusinessFilter(),
    selectedValues: () => api.selectedValues(),
  }
}

describeDictStoreContract('字典缓存契约（useBaseDictSelect.store）', makeStoreTarget)
describeDictSelectContract('字典选择契约（useBaseDictSelect）', makeSelectTarget)
describeDictQueryContract('字典高级查询契约（useBaseDictQuery）', makeQueryTarget)

describePlaceholderFieldContract('占位字段契约（字典投影，06_01 复用）', () => {
  const scope = effectScope()
  const api = scope.run(() => useBaseDictSelect({ storage: undefined })) as UseBaseDictSelectResult
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get disabled() {
      return api.disabled.value
    },
    get requestCount() {
      return api.requestCount.value
    },
    setReady: (value: boolean) => api.setReady(value),
    load: () => {
      void api.load()
    },
  }
})

/**
 * 取桩组件（找不到抛错）。
 *
 * @param wrapper 包装器。
 * @param name 桩组件名。
 */
function findStub(wrapper: VueWrapper, name: string): VueWrapper {
  const found = wrapper.findComponent({ name })
  if (found.exists()) {
    return found as unknown as VueWrapper
  }
  throw new Error(`未找到桩组件：${name}`)
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  globalThis.localStorage.clear()
})

describe('DictSelectField（真实实现）', () => {
  it('占位降级 / 禁用 / 零请求（06_01 冻结契约保持）', () => {
    const stub = createDictSourceStub()
    const wrapper = mount(DictSelectField, {
      props: { modelValue: undefined, ready: false, dictType: 'user_status', source: stub.source },
      global: { stubs },
    })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('字典数据未就绪')
    expect(stub.calls).toEqual([])
  })

  it('展开首屏加载 + 多选上限截断 + 只读回显', async () => {
    const stub = createDictSourceStub()
    const wrapper = mount(DictSelectField, {
      props: { modelValue: undefined, ready: true, dictType: 'user_status', source: stub.source, multiple: true, limit: 1 },
      global: { stubs },
    })
    const select = findStub(wrapper, 'ElSelect')
    select.vm.$emit('visible-change', true)
    await flushPromises()
    expect(stub.calls).toContain('getType')
    expect(wrapper.findAll('[data-test^="dict-option-"]')).toHaveLength(2)

    select.vm.$emit('update:modelValue', ['enabled', 'disabled'])
    await flushPromises()
    expect(wrapper.emitted('limit-exceed')?.[0]?.[0]).toBe(1)
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(['enabled'])

    const readonly = mount(DictSelectField, {
      props: {
        modelValue: ['enabled', 'disabled'],
        ready: true,
        dictType: 'user_status',
        source: stub.source,
        multiple: true,
        readonly: true,
        collapseAfter: 1,
      },
      global: { stubs },
    })
    await flushPromises()
    expect(readonly.find('[data-test="dict-readonly"]').exists()).toBe(true)
    expect(readonly.find('[data-test="dict-tag-overflow"]').text()).toBe('+1')
  })

  it('静态选项兼容通路（未注入数据源）', () => {
    const wrapper = mount(DictSelectField, {
      props: {
        modelValue: 'a',
        ready: true,
        options: [{ label: '甲', value: 'a' }],
      },
      global: { stubs },
    })
    expect(wrapper.findComponent({ name: 'SelectInput' }).exists()).toBe(true)
  })
})

describe('DictLabel（标签回显）', () => {
  it('缓存命中直出 / 未命中回退原值 / 标签形态', async () => {
    const stub = createDictSourceStub()
    const store = new (class extends BaseDictStore {})()
    store.setReady(true)
    bindDictStoreSource(store, stub.source)
    await store.ensureType('user_status')

    const wrapper = mount(DictLabel, {
      props: { value: ['enabled', 'ghost'], dictType: 'user_status', source: stub.source, store, tag: true },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('启用')
    expect(wrapper.text()).toContain('ghost')
  })

  it('未注入数据源原值展示（零请求）', () => {
    const wrapper = mount(DictLabel, {
      props: { value: 'enabled', dictType: 'user_status' },
      global: { stubs },
    })
    expect(wrapper.text()).toBe('enabled')
  })
})

describe('DictCascaderField（字典级联）', () => {
  it('树加载与只读路径回显', async () => {
    const stub = createDictSourceStub()
    const wrapper = mount(DictCascaderField, {
      props: { modelValue: ['zj', 'hz'], ready: true, dictType: 'region', source: stub.source, readonly: true },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="dict-cascader-readonly"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('浙江省')
  })
})

describe('ConditionGroupBuilder（条件组构建）', () => {
  it('增删条件与字段联动', async () => {
    const wrapper = mount(ConditionGroupBuilder, {
      props: {
        modelValue: { logic: 'AND', children: [] },
        fields: [{ field: 'value', label: '值', dataType: 'text', operators: ['eq', 'contains'] }],
      },
      global: { stubs },
    })
    await wrapper.find('[data-test="condition-add"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({
      logic: 'AND',
      children: [{ field: 'value', operator: 'eq' }],
    })
  })
})

describe('DictAdvancedQuery（高级查询抽屉）', () => {
  it('打开加载元数据并执行；应用上抛取项值；取消关闭', async () => {
    const stub = createDictSourceStub()
    const wrapper = mount(DictAdvancedQuery, {
      props: { visible: true, ready: true, dictType: 'user_status', source: stub.source },
      global: { stubs },
    })
    await flushPromises()
    expect(stub.calls).toContain('loadAttrs')
    expect(stub.calls).toContain('advancedQuery')
    expect(wrapper.findAll('[data-test^="dict-adv-result-row-"]')).toHaveLength(2)

    await wrapper.find('[data-test="dict-adv-confirm"]').trigger('click')
    expect(wrapper.emitted('apply')?.[0]?.[0]).toMatchObject({ target: 'items', values: ['enabled', 'disabled'] })

    await wrapper.find('[data-test="dict-adv-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})

describe('工具（HTTP 数据源 / 注册表 / 本地通道 / 翻译器）', () => {
  it('HTTP 数据源：端点与参数 / 解包 / 不可用降级', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void url
      void init
      return new Response(JSON.stringify({ code: 0, data: { version: 1, items: [] } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpDictSource({ endpoint: '/api/v1' })
    await source.getType({ dictType: 'user_status', version: 1, parentId: '' })
    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/api/v1/dicts/user_status')
    expect(url).toContain('version=1')
    expect(url).toContain('parent_id=')
    await source.batch({ types: ['user_status'], locale: 'zh-CN' })
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/v1/dicts/batch')

    vi.stubGlobal('fetch', undefined)
    const degraded = createHttpDictSource()
    expect(await degraded.getType({ dictType: 'x' })).toBeUndefined()
  })

  it('注册表登记与默认键 / 本地通道 / 翻译器', () => {
    registerDictSource('spec-dict', () => createHttpDictSource())
    expect(dictSourceRegistry.get('http')).toBeDefined()
    expect(dictSourceRegistry.get('spec-dict')).toBeDefined()
    expect(localStorageDictChannel).toBeDefined()

    const stub = createDictSourceStub()
    const store = new (class extends BaseDictStore {})()
    store.setReady(true)
    bindDictStoreSource(store, stub.source)
    const translate = createDictTranslator(store)
    expect(translate('user_status', 'enabled')).toBeUndefined()
    return store.ensureType('user_status').then(() => {
      expect(translate('user_status', 'enabled')).toBe('启用')
      expect(translate('user_status', ['enabled', 'disabled'])).toBe('启用、停用')
    })
  })

  it('防抖调度（件层按 300ms 常量驱动）', async () => {
    vi.useFakeTimers()
    const stub = createDictSourceStub()
    const wrapper = mount(DictSelectField, {
      props: { modelValue: undefined, ready: true, dictType: 'user_status', source: stub.source, searchable: true },
      global: { stubs },
    })
    const select = findStub(wrapper, 'ElSelect')
    const remote = (select.props() as Record<string, unknown>).remoteMethod as ((keyword: string) => void) | undefined
    remote?.('启')
    remote?.('启用')
    vi.advanceTimersByTime(DICT_SEARCH_DEBOUNCE + 10)
    await flushPromises()
    expect(stub.calls.filter((call) => call === 'getType')).toHaveLength(1)
  })
})
