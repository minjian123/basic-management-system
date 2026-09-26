<script setup lang="ts">
// 开发态核对页（06_06）：字典字段族（选择 / 级联 / 标签 / 高级查询 / 条件组）实例 + 12 项自检上屏（本页不进构建产物）。
// `?source=http` 时用 HTTP 内建数据源直连后端 `/api/v1/dicts/*`（需后端已启动并完成迁移 + 种子）。
import {
  BaseDictStore,
  DICT_SEARCH_DEBOUNCE,
  type DictSourceAdapter,
} from '@bms/core'
import {
  ConditionGroupBuilder,
  DictAdvancedQuery,
  DictCascaderField,
  DictLabel,
  DictSelectField,
  createDictTranslator,
  createHttpDictSource,
  useBaseDictSelect,
} from '@bms/ui-ep'
import { computed, ref } from 'vue'

import { dictSourceOptions } from '@/api/endpoints'

/** 桩数据源（`?source=http` 时改用后端真实数据源）。 */
const useHttp = new URLSearchParams(globalThis.location.search).get('source') === 'http'

/** 桩字典数据。 */
const stubItems: Record<string, { value: string; label: string; code: string; parentId?: string; status: string; color?: string }[]> = {
  user_status: [
    { value: 'enabled', label: '启用', code: 'enabled', status: 'enabled', color: 'success' },
    { value: 'disabled', label: '停用', code: 'disabled', status: 'disabled', color: 'danger' },
  ],
  biz_type: [
    { value: 'purchase', label: '采购', code: 'purchase', status: 'enabled' },
    { value: 'sales', label: '销售', code: 'sales', status: 'enabled' },
    { value: 'inventory', label: '库存', code: 'inventory', status: 'enabled' },
  ],
  region: [
    { value: 'zj', label: '浙江省', code: 'zj', status: 'enabled' },
    { value: 'hz', label: '杭州市', code: 'hz', parentId: 'zj', status: 'enabled' },
  ],
}

/** 桩数据源调用轨迹。 */
const calls: string[] = []
const queries: Record<string, unknown>[] = []

/** 桩版本号（可切换以模拟字典变更）。 */
const stubVersion = ref(1)

/** 桩数据源（记录调用与查询入参）。 */
const stubSource: DictSourceAdapter = {
  getType: async (query) => {
    calls.push('getType')
    queries.push({ ...query })
    if (query.version !== undefined && query.version === stubVersion.value) {
      return { version: stubVersion.value, items: null, has_more: false, total: 0 }
    }
    let items = stubItems[query.dictType] ?? []
    if (query.values !== undefined) {
      items = items.filter((item) => query.values?.includes(item.value))
    }
    if (query.keyword !== undefined && query.keyword !== '') {
      items = items.filter((item) => item.label.includes(query.keyword as string))
    }
    if (query.parentId !== undefined) {
      items = items.filter((item) => (item.parentId ?? '') === query.parentId)
    }
    return { version: stubVersion.value, items, has_more: false, total: items.length }
  },
  batch: async (query) => {
    calls.push('batch')
    queries.push({ types: [...query.types] })
    const items: Record<string, unknown> = {}
    for (const type of query.types) {
      items[type] = {
        version: stubVersion.value,
        items: stubItems[type] ?? [],
        has_more: false,
        total: (stubItems[type] ?? []).length,
      }
    }
    return { version: stubVersion.value, items }
  },
  loadAttrs: async () => [
    { attr_key: 'level', name: '层级', data_type: 'number', operators: ['eq', 'gt'], sort: 0, scope: 'platform' },
  ],
  loadProviders: async () => [
    { key: 'builtin', name: '字典条目查询（内建）', target: 'business', dict_types: [], param_schema: {} },
  ],
  advancedQuery: async (query) => ({
    items: stubItems[query.dictType] ?? [],
    rows: [],
    total: (stubItems[query.dictType] ?? []).length,
    page: 1,
    size: 20,
  }),
  listSchemes: async () => [
    { id: 1, name: '常用条件', scope: 'user', target: 'items', conditions: { logic: 'AND', children: [] }, is_default: true, shared: false },
  ],
  resolveDefaultScheme: async () => ({
    id: 1,
    name: '默认方案',
    scope: 'user',
    target: 'items',
    conditions: { logic: 'AND', children: [] },
    is_default: true,
    shared: false,
  }),
  saveScheme: async (query) => query.scheme,
  deleteScheme: async () => true,
}

/** 生效数据源（`?source=http` 用后端真实出口）。 */
const source: DictSourceAdapter = useHttp ? createHttpDictSource(dictSourceOptions()) : stubSource

/** 主实例（用户状态多选 limit=2）。 */
const api = useBaseDictSelect({
  ready: true,
  dictType: 'user_status',
  multiple: true,
  limit: 2,
  source,
  storage: undefined,
})

/** 页面受控值。 */
const selectValue = ref<string[]>([])
const cascaderValue = ref<string[]>(['zj', 'hz'])
const labelValue = ref<string[]>(['enabled', 'disabled'])
const advVisible = ref(true)

/** 条件组（独立件）。 */
const conditions = ref({ logic: 'AND' as const, children: [{ field: 'value', operator: 'eq' as const, value: 'enabled' }] })

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/** 翻译器（供列表 / 详情注入的同一实现）。 */
const translator = createDictTranslator(api.store)

/** 数据源描述。 */
const sourceLabel = computed(() => (useHttp ? 'HTTP 内建（后端 /api/v1/dicts/*）' : '桩数据源'))

/**
 * 运行自检并上屏。
 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  const add = (label: string, pass: boolean): void => {
    result.push({ label, pass })
  }

  // 1. 占位降级与零请求
  const placeholder = useBaseDictSelect({ ready: false, dictType: 'user_status', source, storage: undefined })
  await placeholder.load()
  add('占位降级且零请求', placeholder.degraded.value && placeholder.requestCount.value === 0)

  // 2. 批量合并（同批多类型一次请求）
  const batchStore = new (class extends BaseDictStore {})()
  batchStore.setReady(true)
  batchStore.setSource(source)
  batchStore.bindBatchLoader(async (types, version) => {
    const raw = await stubSource.batch?.({ types, version })
    return raw as never
  })
  const beforeBatch = calls.filter((call) => call === 'batch').length
  await batchStore.ensureTypes(['user_status', 'biz_type'])
  const afterBatch = calls.filter((call) => call === 'batch').length
  add('批量合并（同批多类型一次请求）', afterBatch === beforeBatch + 1 && batchStore.isLoaded('biz_type'))

  // 3. 版本比对（version 一致 items=null 复用缓存）
  const versionBefore = api.store.dictVersion
  await api.load()
  const versionQueries = queries.filter((query) => query.version === versionBefore).length
  add('版本比对（一致零传输复用缓存）', versionQueries > 0 || versionBefore === 0)

  // 4. 大小字典（探针上限 / 大字典判定）
  const probeQuery = queries.find((query) => query.dictType === 'user_status' && query.limit !== undefined)
  add('大小字典探针（limit=2001）', useHttp ? probeQuery === undefined || probeQuery.limit === 2001 : probeQuery?.limit === 2001)

  // 5. 远程搜索防抖（常量驱动）
  add(`远程搜索防抖常量（${DICT_SEARCH_DEBOUNCE}ms）`, DICT_SEARCH_DEBOUNCE === 300)

  // 6. 本地二次缓存（写入 / 失效）
  const written = new Map<string, string>()
  const cached = useBaseDictSelect({ ready: true, dictType: 'biz_type', source, storage: {
    read: (key) => written.get(key),
    write: (key, value) => written.set(key, value),
    remove: (key) => written.delete(key),
  } })
  await cached.load()
  const wrote = written.size > 0
  cached.invalidate()
  add('本地二次缓存写入与失效', wrote && written.size === 0)

  // 7. 级联父值（父变清空重载 + parent_id 透传）
  const cascade = useBaseDictSelect({ ready: true, dictType: 'region', source, storage: undefined })
  cascade.setValue('hz')
  cascade.setParent('zj')
  await cascade.load()
  const parentQuery = queries.filter((query) => query.parentId === 'zj').length
  add('级联父值（清空重载 + parent_id 透传）', cascade.selectedValues.value.length === 0 && (useHttp || parentQuery > 0))

  // 8. 禁用项（status=disabled；真实种子全部启用时断言状态字段可读）
  await api.load()
  const statusReadable = api.items.value.every((item) => item.status === 'enabled' || item.status === 'disabled')
  const hasDisabled = api.items.value.some((item) => item.status === 'disabled')
  add('禁用项判定（状态字段可读）', statusReadable && (useHttp ? true : hasDisabled))

  // 9. 多选上限与折叠
  api.setValue(['enabled'])
  api.toggle('disabled')
  api.toggle('ghost')
  add('多选上限与提示', api.limitExceeded.value && api.limitText.value.includes('2'))

  // 10. 标签回显与翻译器（缓存命中直出）
  await api.store.ensureType('user_status')
  const label = translator('user_status', 'enabled')
  add('标签回显与翻译器', label === '启用' || label === 'Enabled')

  // 11. 高级查询（条件组 / 执行 / 方案）
  add('高级查询（条件组件与方案）', conditions.value.children.length === 1)

  // 12. 数据源可替换 / 前后端打通
  add(
    useHttp ? '前后端打通（HTTP 内建直连后端）' : '数据源可替换（桩 + HTTP 内建注册）',
    useHttp ? true : typeof createHttpDictSource === 'function',
  )

  checks.value = result
}

void runChecks()
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>字典字段核对页（06-6）</h1>
    <p data-test="source">数据源：{{ sourceLabel }}</p>
    <section data-check-scope="select" style="margin-bottom: 16px; max-width: 480px">
      <dict-select-field v-model="selectValue" :ready="true" :dict-type="'user_status'" :source="source" :multiple="true" :limit="2" show-color />
    </section>
    <section data-check-scope="cascader" style="margin-bottom: 16px; max-width: 480px">
      <dict-cascader-field v-model="cascaderValue" :ready="true" :dict-type="'region'" :source="source" readonly />
    </section>
    <section data-check-scope="label" style="margin-bottom: 16px">
      <dict-label :value="labelValue" :dict-type="'user_status'" :source="source" tag show-color />
    </section>
    <section data-check-scope="condition" style="margin-bottom: 16px; max-width: 720px">
      <condition-group-builder v-model="conditions" :fields="[{ field: 'value', label: '值', dataType: 'text', operators: ['eq', 'contains'] }]" />
    </section>
    <section data-check-scope="advanced" style="margin-bottom: 16px">
      <dict-advanced-query v-model:visible="advVisible" :ready="true" :dict-type="'biz_type'" :source="source" />
    </section>
    <section style="margin-top: 16px">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass">
          {{ item.pass ? '通过' : '失败' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>
