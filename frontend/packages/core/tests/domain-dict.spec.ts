// kiwi_id: 964
/** 字典领域纯函数用例（06_06）：归一 / 版本三态 / 大小字典 / 值归一与选择 / 标签与过滤 / 树 / 参数与键 / 条件组 / 方案 / 错误码。 */

import { describe, expect, it } from 'vitest'

import {
  DICT_LARGE_THRESHOLD,
  DICT_PROBE_LIMIT,
  applyDictSelection,
  buildDictAdvQuery,
  buildDictBatchQuery,
  buildDictTypeQuery,
  clampDictPage,
  clampDictPageSize,
  defaultOperatorsOf,
  dictAttrFieldOptions,
  dictCacheKey,
  dictFixedFieldOptions,
  dictLabelOf,
  dictSchemePriority,
  dictStorageKey,
  dictSubsetKey,
  dictTranslateValues,
  filterDictItems,
  findDictItem,
  isBlankDictKeyword,
  isDictErrorCode,
  isDictItemDisabled,
  isLargeDict,
  isOperatorAllowed,
  mergeDictItems,
  normalizeConditionGroup,
  normalizeDictBatchResult,
  normalizeDictItem,
  normalizeDictItems,
  normalizeDictKeyword,
  normalizeDictQueryScheme,
  normalizeDictTypeResult,
  normalizeDictValues,
  removeDictValue,
  resolveDictErrorText,
  toDictTreeNodes,
  validateConditionGroup,
  type DictItem,
} from '../src'

const items: DictItem[] = [
  { value: 'enabled', label: '启用', code: 'enabled', sort: 0, status: 'enabled', color: 'success' },
  { value: 'disabled', label: '停用', code: 'disabled', sort: 1, status: 'disabled' },
]

describe('字典领域 · 归一', () => {
  it('条目归一（兼容 snake_case / 缺省补全 / 脏项剔除）', () => {
    expect(normalizeDictItem({ value: 'a', label: '甲' })).toEqual({
      value: 'a',
      label: '甲',
      code: '',
      sort: 0,
      status: 'enabled',
    })
    expect(normalizeDictItem({ value: 'b', parent_id: 'a', status: 'disabled', color: 'danger' })).toMatchObject({
      value: 'b',
      label: 'b',
      parentId: 'a',
      status: 'disabled',
      color: 'danger',
    })
    expect(normalizeDictItem({ label: '无值' })).toBeUndefined()
    expect(normalizeDictItem(null)).toBeUndefined()
    expect(normalizeDictItems([{ value: 'a' }, { label: 'x' }])).toHaveLength(1)
  })

  it('结果三态（items=null 版本一致 / 空数组空字典 / 非空条目集）', () => {
    expect(normalizeDictTypeResult({ version: 3, items: null }).items).toBeNull()
    expect(normalizeDictTypeResult({ version: 3, items: [] }).items).toEqual([])
    const full = normalizeDictTypeResult({ version: 3, items: [{ value: 'a' }], has_more: true, total: 5 })
    expect(full.items).toHaveLength(1)
    expect(full.hasMore).toBe(true)
    expect(full.total).toBe(5)
    const batch = normalizeDictBatchResult({
      version: 2,
      items: { a: null, b: { version: 2, items: [{ value: 'x' }], total: 1 } },
    })
    expect(batch.items.a).toBeNull()
    expect(batch.items.b?.items).toHaveLength(1)
  })

  it('大小字典判定（阈值 / 探针截断）', () => {
    expect(isLargeDict({ version: 1, items: [], hasMore: false, total: DICT_LARGE_THRESHOLD - 1 })).toBe(false)
    expect(isLargeDict({ version: 1, items: [], hasMore: false, total: DICT_LARGE_THRESHOLD })).toBe(true)
    expect(isLargeDict({ version: 1, items: [], hasMore: true, total: 1 })).toBe(true)
    expect(DICT_PROBE_LIMIT).toBe(2001)
  })
})

describe('字典领域 · 值与选择', () => {
  it('受控值归一（单值 / 数组 / 去重 / 空值剔除）', () => {
    expect(normalizeDictValues('a', false)).toEqual(['a'])
    expect(normalizeDictValues(['a', 'a', '', 'b'], true)).toEqual(['a', 'b'])
    expect(normalizeDictValues(['a', 'b'], false)).toEqual(['a'])
    expect(normalizeDictValues(undefined, true)).toEqual([])
    expect(normalizeDictValues([1, 2], true)).toEqual(['1', '2'])
  })

  it('选择与上限（多选去重截断 / 单选替换）', () => {
    const multi = applyDictSelection(['a'], ['b', 'c'], { multiple: true, limit: 2 })
    expect(multi.values).toEqual(['a', 'b'])
    expect(multi.exceeded).toBe(true)
    expect(applyDictSelection(['a'], ['b'], { multiple: false, limit: 0 }).values).toEqual(['b'])
    expect(removeDictValue(['a', 'b'], 'a')).toEqual(['b'])
  })

  it('标签翻译 / 过滤 / 禁用判定', () => {
    expect(dictLabelOf(items, 'enabled')).toBe('启用')
    expect(dictLabelOf(items, 'ghost')).toBeUndefined()
    expect(dictTranslateValues(items, ['enabled', 'ghost'])).toBe('启用、ghost')
    expect(filterDictItems(items, '启').map((item) => item.value)).toEqual(['enabled'])
    expect(filterDictItems(items, 'DISABLED').map((item) => item.value)).toEqual(['disabled'])
    expect(filterDictItems(items, '')).toHaveLength(2)
    expect(isDictItemDisabled(items[1] as DictItem)).toBe(true)
  })

  it('合并与查找（入参覆盖同名项）', () => {
    const merged = mergeDictItems(items, [{ value: 'enabled', label: '启用改', code: '', sort: 0, status: 'enabled' }])
    expect(merged).toHaveLength(2)
    expect(findDictItem(merged, 'enabled')?.label).toBe('启用改')
  })
})

describe('字典领域 · 树', () => {
  it('parentId 构建树（孤儿提升顶层 / 排序）', () => {
    const tree = toDictTreeNodes([
      { value: 'hz', label: '杭州市', code: 'hz', parentId: 'zj', sort: 1, status: 'enabled' },
      { value: 'zj', label: '浙江省', code: 'zj', sort: 0, status: 'enabled' },
      { value: 'orphan', label: '孤儿', code: 'o', parentId: 'ghost', sort: 2, status: 'enabled' },
    ])
    expect(tree.map((node) => node.value)).toEqual(['zj', 'orphan'])
    expect(tree[0]?.children?.map((node) => node.value)).toEqual(['hz'])
  })
})

describe('字典领域 · 参数与键', () => {
  it('单类型 / 批量 / 高级查询线参数（非空才传 / 夹取）', () => {
    expect(buildDictTypeQuery({ dictType: 'a', version: 2, keyword: ' 启 ', parentId: '', values: ['x'], limit: 2001 })).toEqual({
      version: 2,
      keyword: '启',
      parent_id: '',
      values: 'x',
      limit: 2001,
    })
    expect(buildDictTypeQuery({ dictType: 'a', version: 0, keyword: '' })).toEqual({})
    expect(buildDictBatchQuery(['a', 'b'], 1, 'en-US')).toEqual({ types: ['a', 'b'], version: 1, locale: 'en-US' })
    const adv = buildDictAdvQuery('items', { conditions: { logic: 'AND', children: [] }, page: 0, size: 999 })
    expect(adv).toMatchObject({ target: 'items', page: 1, size: 100 })
  })

  it('缓存键与夹取 / 关键词判定', () => {
    expect(dictCacheKey('zh-CN', 'user_status')).toBe('zh-CN:user_status')
    expect(dictSubsetKey('zh-CN', 'user_status', 'enabled')).toBe('zh-CN:user_status:enabled')
    expect(dictStorageKey('zh-CN', 'user_status')).toBe('bms:dict:zh-CN:user_status')
    expect(clampDictPage(0)).toBe(1)
    expect(clampDictPage(2.7)).toBe(2)
    expect(clampDictPageSize(undefined)).toBe(20)
    expect(clampDictPageSize(500)).toBe(100)
    expect(isBlankDictKeyword('  ')).toBe(true)
    expect(normalizeDictKeyword(' 启 ')).toBe('启')
  })
})

describe('字典领域 · 条件组与方案', () => {
  it('操作符联动与字段项', () => {
    expect(defaultOperatorsOf('number')).toContain('between')
    expect(isOperatorAllowed('number', 'contains')).toBe(false)
    expect(isOperatorAllowed('text', 'contains')).toBe(true)
    expect(dictFixedFieldOptions().map((field) => field.field)).toContain('value')
    const attrFields = dictAttrFieldOptions([
      { attrKey: 'level', name: '层级', dataType: 'number', operators: [], sort: 0, scope: 'platform' },
    ])
    expect(attrFields[0]?.field).toBe('attr.level')
    expect(attrFields[0]?.operators).toContain('eq')
  })

  it('条件组归一（结构 / 深度 / 操作符）与业务校验', () => {
    expect(normalizeConditionGroup({ logic: 'OR', children: [{ field: 'value', operator: 'eq', value: 1 }] })).toEqual({
      logic: 'OR',
      children: [{ field: 'value', operator: 'eq', value: 1 }],
    })
    expect(normalizeConditionGroup({ logic: 'AND', children: [{ field: 'value', operator: 'ghost' }] })).toBeUndefined()
    expect(
      normalizeConditionGroup({
        logic: 'AND',
        children: [{ logic: 'AND', children: [{ logic: 'AND', children: [] }] }],
      }),
    ).toBeUndefined()
    const group = { logic: 'AND' as const, children: [{ field: 'attr.ghost', operator: 'eq' as const }] }
    expect(validateConditionGroup(group, dictFixedFieldOptions())).toContain('白名单')
    const allowed = { logic: 'AND' as const, children: [{ field: 'value', operator: 'eq' as const, value: 'a' }] }
    expect(validateConditionGroup(allowed, dictFixedFieldOptions())).toBeUndefined()
  })

  it('方案归一与优先级', () => {
    const scheme = normalizeDictQueryScheme({
      id: 1,
      name: '常用',
      scope: 'tenant',
      target: 'items',
      dict_type: 'region',
      provider_key: 'builtin',
      is_default: true,
    })
    expect(scheme).toMatchObject({ id: 1, name: '常用', scope: 'tenant', dictType: 'region', providerKey: 'builtin', isDefault: true })
    expect(normalizeDictQueryScheme({ name: '', target: 'items' })).toBeUndefined()
    expect(dictSchemePriority('user')).toBeLessThan(dictSchemePriority('tenant'))
    expect(dictSchemePriority('tenant')).toBeLessThan(dictSchemePriority('platform'))
  })
})

describe('字典领域 · 错误码', () => {
  it('错误码判定与文案', () => {
    expect(isDictErrorCode(40102)).toBe(true)
    expect(isDictErrorCode(40104)).toBe(false)
    expect(resolveDictErrorText(40102)).toBe('字典类型不存在')
    expect(resolveDictErrorText(999)).toBe('字典数据源不可用')
  })
})
