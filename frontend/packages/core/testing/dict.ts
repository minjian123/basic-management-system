/**
 * 字典契约（`@bms/core/testing`）。
 *
 * 缓存基类 / 选择族 / 高级查询编排 / 投影为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、批量合并（同批多类型一次请求）、版本一致复用、探针与超大字典、远程搜索、
 * 子集回填（二次零请求）、本地二次缓存通道、选择与上限、级联父值、禁用项、回显、
 * 元数据并行、条件执行、方案 CRUD。
 */

import { describe, expect, it } from 'vitest'

import type { DictConditionGroup, DictItem, DictQueryProvider, DictQueryScheme, DictSourceAdapter } from '../src'

/** 契约条目：用户状态（两条 + 一条停用）。 */
export const DICT_CONTRACT_STATUS: readonly Record<string, unknown>[] = [
  { value: 'enabled', label: '启用', code: 'enabled', sort: 0, status: 'enabled', color: 'success' },
  { value: 'disabled', label: '停用', code: 'disabled', sort: 1, status: 'disabled', color: 'danger' },
]

/** 契约条目：业务类型（三条）。 */
export const DICT_CONTRACT_BIZ: readonly Record<string, unknown>[] = [
  { value: 'purchase', label: '采购', code: 'purchase', sort: 0, status: 'enabled' },
  { value: 'sales', label: '销售', code: 'sales', sort: 1, status: 'enabled' },
  { value: 'inventory', label: '库存', code: 'inventory', sort: 2, status: 'enabled' },
]

/** 契约条目：行政区划（级联：浙江省 → 杭州市）。 */
export const DICT_CONTRACT_REGION: readonly Record<string, unknown>[] = [
  { value: 'zj', label: '浙江省', code: 'zj', sort: 0, status: 'enabled' },
  { value: 'hz', label: '杭州市', code: 'hz', parent_id: 'zj', sort: 1, status: 'enabled' },
]

/** 契约属性 schema。 */
export const DICT_CONTRACT_ATTRS: readonly Record<string, unknown>[] = [
  { attr_key: 'level', name: '层级', data_type: 'number', operators: ['eq', 'gt'], sort: 0, scope: 'platform' },
]

/** 契约提供者。 */
export const DICT_CONTRACT_PROVIDERS: readonly Record<string, unknown>[] = [
  { key: 'builtin', name: '字典条目查询（内建）', target: 'business', dict_types: [], param_schema: {} },
]

/** 数据源桩（记录调用轨迹与查询入参）。 */
export interface DictSourceStub {
  /** 数据源实现。 */
  source: DictSourceAdapter
  /** 调用轨迹。 */
  calls: string[]
  /** 查询入参轨迹。 */
  queries: Record<string, unknown>[]
  /** 当前全局版本号（可修改以模拟字典变更）。 */
  version: number
  /** 大字典类型（桩内按 `has_more` 返回）。 */
  largeTypes: Set<string>
}

/**
 * 创建字典数据源桩（记录调用轨迹；`version` 一致返回 `items=null`）。
 *
 * @param overrides 覆盖方法。
 * @returns 数据源桩。
 */
export function createDictSourceStub(overrides: DictSourceAdapter = {}): DictSourceStub {
  const calls: string[] = []
  const queries: Record<string, unknown>[] = []
  const stub: DictSourceStub = {
    calls,
    queries,
    version: 1,
    largeTypes: new Set<string>(),
    source: {
      getType: async (query) => {
        calls.push('getType')
        queries.push({ ...query })
        if (query.version !== undefined && query.version === stub.version) {
          return { version: stub.version, items: null, has_more: false, total: 0 }
        }
        let items = itemsOf(query.dictType)
        if (query.values !== undefined && query.values.length > 0) {
          items = items.filter((item) => query.values?.includes(String(item.value)))
        }
        if (query.keyword !== undefined && query.keyword !== '') {
          items = items.filter((item) => String(item.label).includes(query.keyword as string))
        }
        if (query.parentId !== undefined) {
          items = items.filter((item) => (item.parent_id ?? '') === query.parentId)
        }
        const large = stub.largeTypes.has(query.dictType)
        const limited = large ? items.slice(0, 1) : items
        return {
          version: stub.version,
          items: limited,
          has_more: large,
          total: items.length,
        }
      },
      batch: async (query) => {
        calls.push('batch')
        queries.push({ types: [...query.types] })
        const items: Record<string, unknown> = {}
        for (const type of query.types) {
          if (query.version !== undefined && query.version === stub.version) {
            items[type] = null
            continue
          }
          items[type] = { version: stub.version, items: itemsOf(type), has_more: false, total: itemsOf(type).length }
        }
        return { version: stub.version, items }
      },
      loadAttrs: async (query) => {
        calls.push('loadAttrs')
        queries.push({ dictType: query.dictType })
        return [...DICT_CONTRACT_ATTRS]
      },
      loadProviders: async (query) => {
        calls.push('loadProviders')
        queries.push({ dictType: query.dictType })
        return [...DICT_CONTRACT_PROVIDERS]
      },
      advancedQuery: async (query) => {
        calls.push('advancedQuery')
        queries.push({ ...query })
        if (query.target === 'business') {
          return { items: [], rows: [{ value: 'purchase', label: '采购' }], total: 1, page: 1, size: 20 }
        }
        return { items: itemsOf(query.dictType), rows: [], total: itemsOf(query.dictType).length, page: 1, size: 20 }
      },
      listSchemes: async (query) => {
        calls.push('listSchemes')
        queries.push({ target: query.target })
        return [
          {
            id: 1,
            name: '常用条件',
            scope: 'user',
            target: 'items',
            dict_type: query.target === 'items' ? 'region' : undefined,
            conditions: { logic: 'AND', children: [] },
            is_default: true,
            shared: false,
          },
        ]
      },
      resolveDefaultScheme: async (query) => {
        calls.push('resolveDefaultScheme')
        queries.push({ target: query.target })
        return {
          id: 1,
          name: '默认方案',
          scope: 'user',
          target: 'items',
          conditions: { logic: 'OR', children: [] },
          is_default: true,
          shared: false,
        }
      },
      saveScheme: async (query) => {
        calls.push('saveScheme')
        queries.push({ name: query.scheme?.name })
        return query.scheme
      },
      deleteScheme: async (query) => {
        calls.push('deleteScheme')
        queries.push({ schemeId: query.schemeId })
        return true
      },
      ...overrides,
    },
  }
  return stub
}

/**
 * 按类型取契约条目。
 *
 * @param dictType 字典类型码。
 * @returns 条目列表。
 */
function itemsOf(dictType: string): Record<string, unknown>[] {
  if (dictType === 'user_status') {
    return [...DICT_CONTRACT_STATUS]
  }
  if (dictType === 'biz_type') {
    return [...DICT_CONTRACT_BIZ]
  }
  if (dictType === 'region') {
    return [...DICT_CONTRACT_REGION]
  }
  return []
}

/** 缓存能力契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface DictStoreContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 已加载类型。 */
  readonly loadedTypes: readonly string[]
  /** 大字典类型。 */
  readonly largeTypes: readonly string[]
  /** 类型缓存条数。 */
  readonly cacheSize: number
  /** 子集缓存条数。 */
  readonly subsetSize: number
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: DictSourceAdapter | undefined): void
  /** 注入 / 移除本地二次缓存通道。 */
  setStorage(channel: unknown): void
  /** 切换语言。 */
  setLocale(locale: string): void
  /** 批量确保加载。 */
  ensureTypes(types: readonly string[]): Promise<void>
  /** 单类型确保加载。 */
  ensureType(dictType: string): Promise<void>
  /** 远程搜索。 */
  searchRemote(dictType: string, keyword: string): Promise<DictItem[]>
  /** 按值回显。 */
  resolveValues(dictType: string, values: readonly string[]): Promise<void>
  /** 同步读条目。 */
  itemsOf(dictType: string): readonly DictItem[]
  /** 按值取标签。 */
  labelOf(dictType: string, value: string): string | undefined
  /** 是否已加载。 */
  isLoaded(dictType: string): boolean
  /** 是否大字典。 */
  isLarge(dictType: string): boolean
  /** 失效。 */
  invalidate(dictType?: string): void
}

/** 选择族契约面。 */
export interface DictSelectContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级态。 */
  readonly degraded: boolean
  /** 请求计数。 */
  readonly requestCount: number
  /** 字典类型码。 */
  readonly dictType: string
  /** 候选与回显条目。 */
  readonly items: readonly DictItem[]
  /** 选中值。 */
  readonly selectedValues: readonly string[]
  /** 是否大字典。 */
  readonly isLarge: boolean
  /** 多选超限标记。 */
  readonly limitExceeded: boolean
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: DictSourceAdapter | undefined): void
  /** 注入 / 移除缓存。 */
  setStore(store: unknown): void
  /** 切换类型。 */
  setDictType(dictType: string): void
  /** 设置关键词。 */
  setKeyword(keyword: string): void
  /** 设置级联父值。 */
  setParent(parentId: string): void
  /** 设置多选。 */
  setMultiple(value: boolean): void
  /** 设置上限。 */
  setLimit(limit: number): void
  /** 设置值。 */
  setValue(value: string | string[] | undefined): void
  /** 选中 / 取消。 */
  toggle(value: string): void
  /** 移除。 */
  remove(value: string): void
  /** 清空。 */
  clearSelection(): void
  /** 加载候选。 */
  load(): Promise<void>
  /** 远程搜索。 */
  searchRemote(keyword: string): Promise<DictItem[]>
  /** 批量回显。 */
  resolve(extra?: readonly string[]): Promise<void>
  /** 失效。 */
  invalidate(): void
  /** 按值取展示文案。 */
  labelOf(value: string): string
  /** 选中回显文本。 */
  selectionText(): string
  /** 上限文案。 */
  limitText(): string
  /** 选项源：按值取文案。 */
  getLabel(value: string | string[]): string | undefined
  /** 选项源：本地搜索。 */
  searchLocal(keyword: string): readonly { value: string; label: string }[]
  /** 选项源：数据版本。 */
  readonly dataVersion: number
}

/** 高级查询契约面。 */
export interface DictQueryContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级态。 */
  readonly degraded: boolean
  /** 请求计数。 */
  readonly requestCount: number
  /** 目标。 */
  readonly target: string
  /** 属性 schema。 */
  readonly attrs: readonly { attrKey: string }[]
  /** 提供者清单。 */
  readonly providers: readonly DictQueryProvider[]
  /** 条件组。 */
  readonly conditions: DictConditionGroup
  /** 取项结果。 */
  readonly results: readonly DictItem[]
  /** 业务筛选行。 */
  readonly rows: readonly Record<string, unknown>[]
  /** 命中总数。 */
  readonly total: number
  /** 错误文案。 */
  readonly errorMessage: string
  /** 方案清单。 */
  readonly schemes: readonly DictQueryScheme[]
  /** 字段项。 */
  readonly fieldOptions: readonly { field: string }[]
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: DictSourceAdapter | undefined): void
  /** 切换类型。 */
  setDictType(dictType: string): void
  /** 切换目标。 */
  setTarget(target: string): void
  /** 设置条件。 */
  setConditions(group: DictConditionGroup): void
  /** 设置提供者。 */
  setProvider(key: string, params?: Record<string, unknown>): void
  /** 设置页码。 */
  setPage(page: number): void
  /** 加载元数据。 */
  loadMeta(): Promise<void>
  /** 执行。 */
  run(): Promise<void>
  /** 重置。 */
  reset(): void
  /** 方案：加载。 */
  loadSchemes(): Promise<void>
  /** 方案：默认解析。 */
  resolveDefaultScheme(): Promise<void>
  /** 方案：应用。 */
  applyScheme(scheme: DictQueryScheme): void
  /** 方案：保存。 */
  saveScheme(name: string): Promise<void>
  /** 方案：删除。 */
  deleteScheme(schemeId: number): Promise<void>
  /** 业务筛选参数。 */
  toBusinessFilter(): Record<string, unknown>
  /** 取项选中值。 */
  selectedValues(): readonly string[]
}

/**
 * 字典缓存契约（`06_06` 冻结；后续移动端复用同一套断言）。
 *
 * 目标约定：`user_status`（两条，含停用）/ `biz_type`（三条）/ `region`（级联两条）；
 * 子集回显 `enabled` 命中、`ghost` 未命中不占位。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeDictStoreContract(name: string, create: () => DictStoreContractTarget): void {
  describe(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setSource(stub.source)
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)

      await target.ensureType('user_status')
      await target.ensureTypes(['biz_type'])
      await target.resolveValues('user_status', ['enabled'])
      expect(target.requestCount).toBe(0)
      expect(stub.calls).toEqual([])
    })

    it('未注入数据源时不请求（就绪亦占位）', async () => {
      const target = create()
      target.setReady(true)
      await target.ensureType('user_status')
      await target.resolveValues('user_status', ['enabled'])
      expect(target.degraded).toBe(false)
      expect(target.requestCount).toBe(0)
    })

    it('单类型加载：探针上限 / 大字典判定 / 缓存命中不重复请求', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)

      await target.ensureType('user_status')
      expect(stub.calls).toEqual(['getType'])
      expect(stub.queries[0]?.limit).toBe(2001)
      expect(target.itemsOf('user_status')).toHaveLength(2)
      expect(target.isLoaded('user_status')).toBe(true)
      expect(target.labelOf('user_status', 'enabled')).toBe('启用')

      await target.ensureType('user_status')
      expect(target.requestCount).toBe(1)

      stub.largeTypes.add('biz_type')
      await target.ensureType('biz_type')
      expect(target.isLarge('biz_type')).toBe(true)
    })

    it('批量合并：同批多类型一次请求；版本一致复用缓存', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)

      await target.ensureTypes(['user_status', 'biz_type'])
      expect(stub.calls).toEqual(['batch'])
      expect(stub.queries[0]?.types).toEqual(['user_status', 'biz_type'])
      expect(target.itemsOf('biz_type')).toHaveLength(3)
      expect(target.requestCount).toBe(1)

      target.invalidate('user_status')
      await target.ensureType('user_status')
      expect(stub.calls.at(-1)).toBe('getType')
      expect(target.isLoaded('user_status')).toBe(true)
    })

    it('子集回显：一次请求、二次零请求、未命中不占位', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)

      await target.resolveValues('user_status', ['enabled', 'ghost'])
      expect(stub.calls).toEqual(['getType'])
      expect(stub.queries[0]?.values).toEqual(['enabled', 'ghost'])
      expect(target.labelOf('user_status', 'enabled')).toBe('启用')
      expect(target.labelOf('user_status', 'ghost')).toBeUndefined()

      await target.resolveValues('user_status', ['enabled', 'ghost'])
      expect(target.requestCount).toBe(1)
    })

    it('本地二次缓存通道：写入 / 失效删除', async () => {
      const target = create()
      const stub = createDictSourceStub()
      const written = new Map<string, string>()
      const removed: string[] = []
      target.setReady(true)
      target.setSource(stub.source)
      target.setStorage({
        read: (key: string) => written.get(key),
        write: (key: string, value: string) => written.set(key, value),
        remove: (key: string) => {
          removed.push(key)
          written.delete(key)
        },
      })

      await target.ensureType('user_status')
      expect([...written.keys()]).toEqual(['bms:dict:zh-CN:user_status'])
      target.invalidate('user_status')
      expect(removed).toEqual(['bms:dict:zh-CN:user_status'])
      expect(target.cacheSize).toBe(0)
    })
  })
}

/**
 * 字典选择族契约。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeDictSelectContract(name: string, create: () => DictSelectContractTarget): void {
  describe(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setSource(stub.source)
      expect(target.degraded).toBe(true)
      await target.load()
      await target.resolve(['enabled'])
      expect(target.requestCount).toBe(0)
      expect(stub.calls).toEqual([])
    })

    it('小字典全量加载与本地过滤', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('user_status')

      await target.load()
      expect(target.items).toHaveLength(2)
      expect(target.labelOf('disabled')).toBe('停用')
      expect(target.items.some((item) => item.status === 'disabled')).toBe(true)

      target.setKeyword('启')
      await target.load()
      expect(target.items.map((item) => item.value)).toEqual(['enabled'])
    })

    it('大字典远程搜索与禁用项', async () => {
      const target = create()
      const stub = createDictSourceStub()
      stub.largeTypes.add('user_status')
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('user_status')

      await target.load()
      expect(target.isLarge).toBe(true)
      expect(stub.calls.at(-1)).toBe('getType')
      expect(target.items).toHaveLength(1)

      await target.searchRemote('启')
      expect(target.items.map((item) => item.value)).toEqual(['enabled'])
    })

    it('级联父值：父变清空值并重载（参数透传）', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('region')

      target.setValue('hz')
      await target.load()
      expect(target.selectedValues).toEqual(['hz'])

      target.setParent('zj')
      expect(target.selectedValues).toEqual([])
      await target.load()
      expect(stub.queries.at(-1)?.parentId).toBe('zj')
      expect(target.items.map((item) => item.value)).toEqual(['hz'])
    })

    it('多选去重 / 上限截断 / 移除 / 清空', () => {
      const target = create()
      target.setMultiple(true)
      target.setLimit(2)
      target.toggle('a')
      target.toggle('a')
      expect(target.selectedValues).toEqual([])
      target.toggle('a')
      target.toggle('b')
      expect(target.selectedValues).toEqual(['a', 'b'])
      target.toggle('c')
      expect(target.limitExceeded).toBe(true)
      expect(target.selectedValues).toEqual(['a', 'b'])
      expect(target.limitText()).toContain('2')
      target.remove('a')
      expect(target.selectedValues).toEqual(['b'])
      target.clearSelection()
      expect(target.selectedValues).toEqual([])
      expect(target.selectionText()).toBe('—')
    })

    it('批量回显：命中 label / 未命中回退值 / 选项源语义', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('user_status')

      target.setValue(['enabled', 'ghost'])
      await target.resolve()
      expect(target.labelOf('enabled')).toBe('启用')
      expect(target.labelOf('ghost')).toBe('ghost')
      expect(target.getLabel(['enabled', 'ghost'])).toBe('启用、ghost')
      expect(target.searchLocal('启').map((item) => item.value)).toEqual(['enabled'])
      expect(target.dataVersion).toBeGreaterThan(0)
    })
  })
}

/**
 * 字典高级查询契约。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeDictQueryContract(name: string, create: () => DictQueryContractTarget): void {
  describe(name, () => {
    it('未就绪 / 未注入时不请求', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setSource(stub.source)
      expect(target.degraded).toBe(true)
      await target.loadMeta()
      await target.run()
      expect(target.requestCount).toBe(0)
      expect(stub.calls).toEqual([])
    })

    it('元数据并行加载（attrs + providers）与字段项', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('region')

      await target.loadMeta()
      expect(stub.calls).toEqual(['loadAttrs', 'loadProviders'])
      expect(target.attrs.map((attr) => attr.attrKey)).toEqual(['level'])
      expect(target.providers.map((provider) => provider.key)).toEqual(['builtin'])
      expect(target.fieldOptions.map((field) => field.field)).toContain('attr.level')
    })

    it('条件执行（取项）与非法条件拒绝', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('user_status')

      await target.run()
      expect(target.results).toHaveLength(2)
      expect(target.total).toBe(2)

      const before = stub.calls.length
      target.setConditions({ logic: 'AND', children: [{ field: 'attr.ghost', operator: 'eq', value: 1 }] })
      await target.run()
      expect(stub.calls.length).toBe(before)
      expect(target.errorMessage).not.toBe('')
    })

    it('业务筛选：提供者与参数透传', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('biz_type')
      target.setTarget('business')
      target.setProvider('builtin', { keyword: '采购' })

      await target.run()
      expect(stub.queries.at(-1)?.target).toBe('business')
      expect(stub.queries.at(-1)?.provider).toBe('builtin')
      expect(stub.queries.at(-1)?.params).toEqual({ keyword: '采购' })
      expect(target.rows).toHaveLength(1)
      expect(target.toBusinessFilter().provider).toBe('builtin')
    })

    it('方案：加载 / 默认解析 / 应用 / 保存 / 删除', async () => {
      const target = create()
      const stub = createDictSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setDictType('region')

      await target.loadSchemes()
      expect(target.schemes).toHaveLength(1)
      await target.resolveDefaultScheme()
      expect(target.conditions.logic).toBe('OR')
      target.applyScheme({ name: 'x', scope: 'user', target: 'items', isDefault: false, shared: false, providerKey: 'builtin' })
      expect(target.toBusinessFilter().provider).toBe('builtin')
      await target.saveScheme('新方案')
      expect(stub.calls).toContain('saveScheme')
      await target.deleteScheme(1)
      expect(stub.calls).toContain('deleteScheme')
    })
  })
}
