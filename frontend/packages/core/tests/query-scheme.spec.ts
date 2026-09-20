/** 查询方案组件基类（`BaseQueryScheme`：条件模型 / 序列化 / 失效剔除 / 方案 CRUD / 三级优先级）+ 契约套件。 */

import { describeQuerySchemeContract, type QuerySchemeContractTarget } from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

import { BasePersistedState, BaseQueryScheme, type FilterField } from '../src'

/** 具体查询方案件（可实例化）。 */
class DemoQuery extends BaseQueryScheme {}

/** 契约目标：查询方案基类实例。 */
function makeTarget(): QuerySchemeContractTarget {
  const scheme = new DemoQuery()
  return {
    get conditions() {
      return scheme.conditions
    },
    get keyword() {
      return scheme.keyword
    },
    get schemes() {
      return scheme.schemes
    },
    get activeScheme() {
      return scheme.activeScheme
    },
    get defaultSchemeName() {
      return scheme.defaultScheme?.name
    },
    setConditions: (conditions) => scheme.setConditions(conditions),
    setKeyword: (value) => scheme.setKeyword(value),
    resetConditions: () => scheme.resetConditions(),
    queryParams: () => scheme.queryParams(),
    prune: (fields) => scheme.prune(fields),
    setSchemes: (entries) => scheme.setSchemes(entries),
    saveScheme: (entry) => scheme.saveScheme({ ...entry, conditions: [...entry.conditions] }),
    applyScheme: (name) => scheme.applyScheme(name),
    removeScheme: (name) => scheme.removeScheme(name),
    renameScheme: (oldName, newName) => scheme.renameScheme(oldName, newName),
    setDefaultScheme: (name) => scheme.setDefaultScheme(name),
  }
}

describeQuerySchemeContract('查询方案契约（BaseQueryScheme）', makeTarget)

describe('BaseQueryScheme 继承与身份', () => {
  it('继承偏好持久化能力基类', () => {
    const scheme = new DemoQuery()
    expect(scheme).toBeInstanceOf(BasePersistedState)
    expect(scheme.identifier).toBe('query-scheme')
    expect(scheme.key).toBe('query-scheme')
  })
})

describe('BaseQueryScheme 条件模型', () => {
  it('默认条件种子与重置', () => {
    const scheme = new DemoQuery()
    scheme.setDefaults([{ field: 'status', operator: 'eq', value: 'enabled' }])
    expect(scheme.conditions).toEqual([{ field: 'status', operator: 'eq', value: 'enabled' }])
    scheme.setConditions([{ field: 'a', operator: 'eq', value: 1 }])
    scheme.setKeyword('张')
    scheme.resetConditions()
    expect(scheme.keyword).toBe('')
    expect(scheme.conditions).toEqual([{ field: 'status', operator: 'eq', value: 'enabled' }])
  })

  it('生效条件与查询参数', () => {
    const scheme = new DemoQuery()
    scheme.setConditions([
      { field: 'a', operator: 'eq', value: 1 },
      { field: 'b', operator: 'like', value: '' },
    ])
    expect(scheme.activeConditions()).toEqual([{ field: 'a', operator: 'eq', value: 1 }])
    expect(scheme.queryParams()).toEqual({ a: 1 })
    scheme.setKeyword('x')
    expect(scheme.keyword).toBe('x')
    scheme.setKeyword('x')
    expect(scheme.queryParams()).toEqual({ a: 1, keyword: 'x' })
  })

  it('失效剔除回写条件', () => {
    const scheme = new DemoQuery()
    scheme.setConditions([
      { field: 'gone', operator: 'eq', value: 1 },
      { field: 'status', operator: 'eq', value: 'enabled' },
    ])
    const fields: FilterField[] = [{ key: 'status', label: '状态', type: 'select' }]
    expect(scheme.prune(fields)).toBe(1)
    expect(scheme.conditions).toEqual([{ field: 'status', operator: 'eq', value: 'enabled' }])
    expect(scheme.prune(fields)).toBe(0)
  })
})

describe('BaseQueryScheme 方案管理', () => {
  it('保存 / 应用 / 删除 / 重命名', () => {
    const scheme = new DemoQuery()
    scheme.saveScheme({ name: '默认', conditions: [{ field: 'a', operator: 'eq', value: 1 }] })
    scheme.saveScheme({ name: '默认', conditions: [{ field: 'b', operator: 'eq', value: 2 }] })
    expect(scheme.schemes).toHaveLength(1)
    expect(scheme.schemes[0]?.scope).toBe('user')

    expect(scheme.applyScheme('默认')).toEqual([{ field: 'b', operator: 'eq', value: 2 }])
    expect(scheme.applyScheme('缺失')).toBeUndefined()

    expect(scheme.renameScheme('缺失', 'x')).toBe(false)
    expect(scheme.renameScheme('默认', '')).toBe(false)
    expect(scheme.renameScheme('默认', '我的')).toBe(true)
    expect(scheme.activeScheme).toBe('我的')
    scheme.saveScheme({ name: '另一', conditions: [] })
    expect(scheme.renameScheme('另一', '我的')).toBe(false)

    expect(scheme.removeScheme('我的')).toBe(true)
    expect(scheme.activeScheme).toBeUndefined()
    expect(scheme.removeScheme('我的')).toBe(false)
  })

  it('作用域分组与默认解析（三级优先级）', () => {
    const scheme = new DemoQuery()
    scheme.setSchemes([
      { name: 'p', scope: 'platform', target: 'business', conditions: [], isDefault: true },
      { name: 't', scope: 'tenant', target: 'business', conditions: [] },
      { name: 'u', scope: 'user', target: 'business', conditions: [], isDefault: true },
    ])
    expect(scheme.schemesByScope('tenant').map((item) => item.name)).toEqual(['t'])
    expect(scheme.resolveDefault()?.name).toBe('u')
    expect(scheme.defaultScheme?.name).toBe('u')

    scheme.setDefaultScheme('t')
    expect(scheme.defaultScheme?.name).toBe('t')
    scheme.setDefaultScheme(undefined)
    expect(scheme.defaultScheme).toBeUndefined()
  })

  it('从原始值归一方案清单', () => {
    const scheme = new DemoQuery()
    scheme.normalizeSchemes([{ name: 'a', conditions: [{ field: 'x', operator: 'eq', value: 1 }] }, null])
    expect(scheme.schemes).toHaveLength(1)
    expect(scheme.schemes[0]).toMatchObject({ name: 'a', scope: 'user', isDefault: false })
  })
})
