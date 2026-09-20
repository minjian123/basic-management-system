/** 领域纯函数：筛选与查询方案（操作符 / 序列化 / 摘要 / 失效剔除 / 方案优先级）。 */

import { describe, expect, it } from 'vitest'

import {
  FIELD_QUERY_OPERATORS,
  FILTER_OPERATORS,
  FILTER_OPERATOR_LABELS,
  buildQueryParams,
  conditionText,
  defaultOperatorOf,
  fieldOf,
  hasSchemeName,
  isConditionActive,
  normalizeConditions,
  normalizeSchemeEntry,
  normalizeSchemes,
  operatorsOf,
  pruneConditions,
  resolveDefaultScheme,
  resolveScheme,
  schemePriority,
  serializeCondition,
  serializeConditions,
  summarizeConditions,
  toConditionValue,
  validateConditionRange,
  type FilterField,
} from '../src'

describe('筛选操作符', () => {
  it('白名单与后端同源（11 种，含 like / is_not_null，无 contains / not_in）', () => {
    expect(FILTER_OPERATORS).toHaveLength(11)
    expect(FILTER_OPERATORS).toContain('like')
    expect(FILTER_OPERATORS).toContain('is_not_null')
    expect(FILTER_OPERATORS).not.toContain('contains')
    expect(FILTER_OPERATORS).not.toContain('not_in')
    expect(FIELD_QUERY_OPERATORS.every((operator) => FILTER_OPERATORS.includes(operator))).toBe(true)
    expect(Object.keys(FILTER_OPERATOR_LABELS)).toHaveLength(FILTER_OPERATORS.length)
  })

  it('按字段类型取缺省操作符与可选操作符', () => {
    expect(defaultOperatorOf('text')).toBe('like')
    expect(defaultOperatorOf('multi_select')).toBe('in')
    expect(defaultOperatorOf('number')).toBe('between')
    expect(defaultOperatorOf('switch')).toBe('eq')
    expect(operatorsOf(undefined)).toEqual(FIELD_QUERY_OPERATORS)
    expect(operatorsOf({ key: 'a', label: 'A', type: 'number' })[0]).toBe('between')
    expect(operatorsOf({ key: 'a', label: 'A', type: 'text', operators: ['eq', 'like'] })).toEqual(['eq', 'like'])
    expect(fieldOf([{ key: 'a', label: 'A', type: 'text' }], 'a')?.label).toBe('A')
    expect(fieldOf([], 'a')).toBeUndefined()
  })
})

describe('条件归一与生效判定', () => {
  it('归一剔除脏项并补缺省操作符', () => {
    expect(normalizeConditions(undefined)).toEqual([])
    expect(
      normalizeConditions([null, 1, { field: '  ' }, { field: 'a' }, { field: 'b', operator: '', value: 1 }]),
    ).toEqual([
      { field: 'a', operator: 'eq', value: undefined },
      { field: 'b', operator: 'eq', value: 1 },
    ])
  })

  it('空条件不参与请求', () => {
    expect(isConditionActive({ field: 'a', operator: 'eq', value: '' })).toBe(false)
    expect(isConditionActive({ field: 'a', operator: 'eq', value: null })).toBe(false)
    expect(isConditionActive({ field: 'a', operator: 'eq', value: 0 })).toBe(true)
    expect(isConditionActive({ field: 'a', operator: 'like', value: 'x' })).toBe(true)
    expect(isConditionActive({ field: 'a', operator: 'is_null', value: null })).toBe(true)
    expect(isConditionActive({ field: '', operator: 'eq', value: 1 })).toBe(false)
  })
})

describe('条件序列化（与后端逐分支一致）', () => {
  it('等值 / 多值 / 区间 / 空值标记', () => {
    expect(serializeCondition({ field: 'status', operator: 'eq', value: 'enabled' })).toEqual({ status: 'enabled' })
    expect(serializeCondition({ field: 'tags', operator: 'in', value: ['a', 'b'] })).toEqual({ tags: 'a,b' })
    expect(serializeCondition({ field: 'created', operator: 'between', value: ['s', 'e'] })).toEqual({
      created_start: 's',
      created_end: 'e',
    })
    expect(serializeCondition({ field: 'phone', operator: 'is_null', value: null })).toEqual({ phone_is_null: '1' })
    expect(serializeCondition({ field: 'email', operator: 'is_not_null', value: null })).toEqual({
      email_is_not_null: '1',
    })
    expect(serializeCondition({ field: 'n', operator: 'between', value: ['1'] })).toEqual({ n: ['1'] })
  })

  it('清单序列化与关键字合并（空条件 / 空关键字不传）', () => {
    expect(
      serializeConditions([
        { field: 'a', operator: 'eq', value: 1 },
        { field: 'a', operator: 'eq', value: 2 },
        { field: 'b', operator: 'like', value: '' },
      ]),
    ).toEqual({ a: 2 })
    expect(buildQueryParams([{ field: 'a', operator: 'eq', value: 1 }], '  ')).toEqual({ a: 1 })
    expect(buildQueryParams([{ field: 'a', operator: 'eq', value: 1 }], ' 张 ')).toEqual({ a: 1, keyword: '张' })
  })
})

describe('条件摘要', () => {
  const fields: FilterField[] = [
    { key: 'status', label: '状态', type: 'select', options: [{ label: '启用', value: 'enabled' }] },
    { key: 'created', label: '创建时间', type: 'date' },
    { key: 'dept', label: '部门', type: 'dept', includeChildren: true },
  ]

  it('按操作符与字段类型生成文案', () => {
    expect(conditionText({ field: 'status', operator: 'eq', value: 'enabled' }, fields[0])).toBe('状态：启用')
    expect(
      conditionText({ field: 'created', operator: 'between', value: ['2026-09-01', '2026-09-12'] }, fields[1]),
    ).toContain('创建时间：')
    expect(conditionText({ field: 'dept', operator: 'eq', value: '研发中心' }, fields[2])).toBe(
      '部门：研发中心（含下级）',
    )
    expect(conditionText({ field: 'keyword', operator: 'like', value: '张' }, undefined)).toBe('关键字：张')
    expect(conditionText({ field: 'x', operator: 'is_null', value: null }, undefined)).toBe('x：为空')
    expect(conditionText({ field: 'x', operator: 'in', value: [] }, undefined)).toBe('x：—')
  })

  it('仅出已生效条件', () => {
    const summaries = summarizeConditions(
      [
        { field: 'status', operator: 'eq', value: 'enabled' },
        { field: 'created', operator: 'eq', value: '' },
      ],
      fields,
    )
    expect(summaries).toEqual([{ field: 'status', label: '状态', text: '状态：启用' }])
  })
})

describe('失效剔除与区间校验', () => {
  const fields: FilterField[] = [
    { key: 'status', label: '状态', type: 'select', options: [{ label: '启用', value: 'enabled' }] },
    { key: 'remark', label: '备注', type: 'text', query: false },
  ]

  it('字段缺失 / 非查询类 / 选项失效均剔除', () => {
    const result = pruneConditions(
      [
        { field: 'gone', operator: 'eq', value: 1 },
        { field: 'remark', operator: 'like', value: 'x' },
        { field: 'status', operator: 'eq', value: 'removed_option' },
        { field: 'status', operator: 'eq', value: 'enabled' },
      ],
      fields,
    )
    expect(result.removed).toBe(3)
    expect(result.conditions).toEqual([{ field: 'status', operator: 'eq', value: 'enabled' }])
    expect(pruneConditions([{ field: 'x', operator: 'eq', value: 1 }], []).removed).toBe(0)
  })

  it('区间与数值校验', () => {
    const numberField: FilterField = { key: 'amount', label: '金额', type: 'number' }
    expect(validateConditionRange({ field: 'amount', operator: 'between', value: [10, 5] }, numberField)).toBe(
      '区间起始值不能大于结束值',
    )
    expect(validateConditionRange({ field: 'amount', operator: 'between', value: ['a', 5] }, numberField)).toBe(
      '请输入有效数值',
    )
    expect(validateConditionRange({ field: 'amount', operator: 'between', value: [1, 5] }, numberField)).toBeUndefined()
    expect(validateConditionRange({ field: 'amount', operator: 'gt', value: 'x' }, numberField)).toBe('请输入有效数值')
    expect(validateConditionRange({ field: 'amount', operator: 'gt', value: 1 }, numberField)).toBeUndefined()

    const dateField: FilterField = { key: 'd', label: '日期', type: 'date' }
    expect(
      validateConditionRange({ field: 'd', operator: 'between', value: ['2026-09-12', '2026-09-01'] }, dateField),
    ).toBe('区间起始值不能大于结束值')
    expect(toConditionValue({ field: 'a', operator: 'eq', value: 1 }, 2)).toEqual({
      field: 'a',
      operator: 'eq',
      value: 2,
    })
  })
})

describe('查询方案（归一与优先级）', () => {
  it('作用域优先级（个人 > 租户 > 平台）', () => {
    expect(schemePriority('user')).toBe(2)
    expect(schemePriority('tenant')).toBe(1)
    expect(schemePriority('platform')).toBe(0)
  })

  it('归一方案条目与清单', () => {
    expect(normalizeSchemeEntry(null)).toBeUndefined()
    expect(normalizeSchemeEntry({ name: '  ' })).toBeUndefined()
    const entry = normalizeSchemeEntry({
      name: '我负责的',
      scope: 'bad',
      target: 'bad',
      conditions: [{ field: 'a', operator: 'eq', value: 1 }],
    })
    expect(entry).toMatchObject({ name: '我负责的', scope: 'user', target: 'business', isDefault: false })

    expect(
      normalizeSchemes([{ name: 'a' }, { name: '' }, { name: 'b', scope: 'tenant', isDefault: true }]).map(
        (item) => item.name,
      ),
    ).toEqual(['a', 'b'])
    expect(normalizeSchemes('bad')).toEqual([])
  })

  it('按名解析与默认方案', () => {
    const schemes = normalizeSchemes([
      { name: 'p', scope: 'platform', isDefault: true, conditions: [] },
      { name: 'u', scope: 'user', isDefault: true, conditions: [] },
      { name: 'x', scope: 'tenant', conditions: [] },
    ])
    expect(resolveScheme(schemes, 'x')?.name).toBe('x')
    expect(resolveScheme(schemes, 'absent')).toBeUndefined()
    expect(resolveDefaultScheme(schemes)?.name).toBe('u')
    expect(resolveDefaultScheme(normalizeSchemes([{ name: 'a', conditions: [] }]))).toBeUndefined()
    expect(hasSchemeName(schemes, 'u')).toBe(true)
    expect(hasSchemeName(schemes, 'absent')).toBe(false)
  })
})
