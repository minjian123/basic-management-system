/** 领域纯函数：列表偏好（键 / 结构归一 / 列双向映射 / 条件子键 / 失效剔除 / 体积保护）。 */

import { describe, expect, it } from 'vitest'

import {
  LIST_DENSITIES,
  LIST_PREF_KEY_PREFIX,
  LIST_PREF_MAX_CONDITIONS,
  PAGE_SIZE_DEFAULT,
  buildListPrefKey,
  emptyListPreference,
  fromColumnPreferences,
  isListPreferenceOversized,
  listPreferenceBytes,
  normalizeListPreference,
  pruneListPreference,
  toColumnPreferences,
  trimListPreference,
  withQuery,
  withoutQuery,
  type FilterField,
  type ListPreference,
  type TableColumn,
} from '../src'

describe('列表偏好键与缺省结构', () => {
  it('键为 list.{form_key}', () => {
    expect(buildListPrefKey('user_form')).toBe('list.user_form')
    expect(buildListPrefKey(' user_form ')).toBe('list.user_form')
    expect(buildListPrefKey('')).toBe(LIST_PREF_KEY_PREFIX)
  })

  it('缺省结构与密度取值', () => {
    expect(LIST_DENSITIES).toEqual(['default', 'small'])
    expect(emptyListPreference()).toEqual({
      columns: [],
      page_size: PAGE_SIZE_DEFAULT,
      density: 'default',
      query: { conditions: [] },
    })
  })
})

describe('结构归一', () => {
  it('脏值回落缺省并夹取页长', () => {
    expect(normalizeListPreference(null)).toEqual(emptyListPreference())
    const normalized = normalizeListPreference({
      columns: [null, { prop: 'a' }, { prop: 'a' }, { prop: 'b', visible: false, width: 120 }],
      page_size: 9999,
      density: 'loose',
      query: { keyword: '', conditions: [{ field: 'x', operator: 'eq', value: 1 }] },
    })
    expect(normalized.page_size).toBe(200)
    expect(normalized.density).toBe('default')
    expect(normalized.columns.map((column) => column.prop)).toEqual(['a', 'b'])
    expect(normalized.columns[1]).toMatchObject({ visible: false, width: 120 })
    expect(normalized.query.keyword).toBeUndefined()
    expect(normalized.query.conditions).toEqual([{ field: 'x', operator: 'eq', value: 1 }])
    expect(normalizeListPreference({ page_size: 0 }).page_size).toBe(1)
    expect(normalizeListPreference({ page_size: 'bad' }).page_size).toBe(PAGE_SIZE_DEFAULT)
  })
})

describe('列偏好双向映射', () => {
  const columns: TableColumn[] = [
    { key: 'a', title: 'A' },
    { key: 'b', title: 'B', width: 120 },
    { key: 'c', title: 'C', visible: false },
  ]

  it('列状态 → 偏好列', () => {
    expect(
      toColumnPreferences([
        { key: 'a', visible: true, order: 1 },
        { key: 'b', visible: false, order: 0, width: 100 },
      ]),
    ).toEqual([
      { prop: 'a', visible: true, order: 1, width: undefined },
      { prop: 'b', visible: false, order: 0, width: 100 },
    ])
  })

  it('偏好列 → 列状态（剔除已删列、按偏好重排、追加新增列）', () => {
    const states = fromColumnPreferences(
      [
        { prop: 'b', visible: true, order: 0, width: 100 },
        { prop: 'gone', visible: true, order: 1 },
      ],
      columns,
    )
    expect(states.map((state) => state.key)).toEqual(['b', 'a', 'c'])
    expect(states[0]).toMatchObject({ visible: true, width: 100, order: 0 })
    expect(states[1]).toMatchObject({ visible: true, order: 1 })
    expect(states[2]).toMatchObject({ visible: false, order: 2 })
    expect(fromColumnPreferences([], columns).map((state) => state.key)).toEqual(['a', 'b', 'c'])
  })
})

describe('条件子键读写与失效剔除', () => {
  const base = emptyListPreference()

  it('写入与清除', () => {
    const written = withQuery(base, [{ field: 'status', operator: 'eq', value: 'enabled' }], '张')
    expect(written.query).toEqual({
      keyword: '张',
      conditions: [{ field: 'status', operator: 'eq', value: 'enabled' }],
    })
    expect(withQuery(base, [], '').query).toEqual({ keyword: undefined, conditions: [] })
    const cleared = withoutQuery(written)
    expect(cleared.query).toEqual({ conditions: [] })
  })

  it('条件与列按声明剔除并计数', () => {
    const preference: ListPreference = {
      ...base,
      columns: [
        { prop: 'a', visible: true, order: 0 },
        { prop: 'gone', visible: true, order: 1 },
      ],
      query: {
        conditions: [
          { field: 'gone', operator: 'eq', value: 1 },
          { field: 'status', operator: 'eq', value: 'enabled' },
        ],
      },
    }
    const fields: FilterField[] = [{ key: 'status', label: '状态', type: 'select' }]
    const result = pruneListPreference(preference, fields, [{ key: 'a', title: 'A' }])
    expect(result.removedConditions).toBe(1)
    expect(result.removedColumns).toBe(1)
    expect(result.preference.columns.map((column) => column.prop)).toEqual(['a'])
    expect(result.preference.query.conditions).toEqual([{ field: 'status', operator: 'eq', value: 'enabled' }])
  })
})

describe('体积保护', () => {
  it('字节估算 / 超限判定 / 裁剪', () => {
    const small = emptyListPreference()
    expect(listPreferenceBytes(small)).toBeGreaterThan(0)
    expect(isListPreferenceOversized(small)).toBe(false)
    expect(trimListPreference(small)).toEqual(small)

    const hidden = Array.from({ length: 2000 }, (_item, index) => ({
      prop: `hidden_${index}_padpadpadpadpadpad`,
      visible: false,
      order: index,
    }))
    const oversized: ListPreference = { ...small, columns: hidden }
    expect(isListPreferenceOversized(oversized)).toBe(true)
    expect(trimListPreference(oversized).columns).toEqual([])
  })

  it('裁剪条件数上限（列不可再裁时截断条件）', () => {
    const conditions = Array.from({ length: 80 }, (_item, index) => ({
      field: `f${index}_${'p'.repeat(900)}`,
      operator: 'eq',
      value: index,
    }))
    const oversized: ListPreference = { ...emptyListPreference(), columns: [], query: { conditions } }
    expect(isListPreferenceOversized(oversized)).toBe(true)
    expect(trimListPreference(oversized).query.conditions).toHaveLength(LIST_PREF_MAX_CONDITIONS)
  })
})
