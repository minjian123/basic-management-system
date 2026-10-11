// kiwi_id: 2291
/**
 * 契约用例：通用页面路由能力基类 `BasePageRoute`（02_13）。
 *
 * 覆盖：声明登记 / 解析（路由 + 视图 + 表单框架配置 + 数据源 + 联动键）、
 * 清单归一（裸数组与 `{items}` 包装）、`form_key → data_source_key` 多对一（显式覆盖 / 清单命中 / 未登记不可用）、
 * 未注入适配器占位零请求、装载与重置。
 */

import { describe, expect, it } from 'vitest'

import {
  BasePageRoute,
  normalizeDataSourceRecords,
  normalizeFormKeyRecords,
  resolvePageRoute,
  type FormPageDeclaration,
} from '../src/index'

/** 具体页面路由（可实例化）。 */
class PageRoute extends BasePageRoute {}

const DATA_SOURCES = {
  items: [
    {
      data_source_key: 'role',
      name: '角色',
      kind: 'dict',
      data_source: 'platform',
      origin: 'platform',
      allowlist: ['code'],
      cascade: false,
      strategies: ['select'],
      status: 'enabled',
    },
    {
      data_source_key: 'user',
      name: '用户',
      kind: 'dict',
      data_source: 'platform',
      origin: 'platform',
      allowlist: ['code'],
      cascade: false,
      strategies: ['select'],
      status: 'enabled',
    },
  ],
}

const FORM_KEYS = {
  items: [
    { form_key: 'role', name: '角色', kind: 'dict', table: 'sys_role', data_source_key: 'role', status: 'enabled' },
    { form_key: 'user', name: '用户', kind: 'dict', table: 'sys_user', data_source_key: 'user', status: 'enabled' },
  ],
}

const ROLE_DECL: FormPageDeclaration = {
  formKey: 'role',
  title: '角色管理',
  path: '/sys/roles',
  name: 'SystemRole',
  meta: { keepAlive: true },
  list: () => Promise.resolve({}),
}

describe('domain/page-route 清单归一', () => {
  it('兼容裸数组与 {items} 包装，snake_case 映射，脏项剔除', () => {
    expect(normalizeDataSourceRecords(DATA_SOURCES.items)).toHaveLength(2)
    const wrapped = normalizeDataSourceRecords(DATA_SOURCES)
    expect(wrapped.map((item) => item.dataSourceKey)).toEqual(['role', 'user'])
    expect(wrapped[0]?.origin).toBe('platform')
    expect(wrapped[0]?.strategies).toEqual(['select'])
    // 脏项（缺标识）剔除
    expect(normalizeDataSourceRecords([{ name: 'x' }, ...DATA_SOURCES.items])).toHaveLength(2)
    expect(normalizeFormKeyRecords(FORM_KEYS)[0]).toMatchObject({ formKey: 'role', dataSourceKey: 'role' })
  })
})

describe('domain/page-route 页面解析', () => {
  it('数据源取清单命中值，并派生联动键', () => {
    const resolution = resolvePageRoute(ROLE_DECL, normalizeFormKeyRecords(FORM_KEYS), normalizeDataSourceRecords(DATA_SOURCES))
    expect(resolution).toBeDefined()
    expect(resolution?.dataSourceKey).toBe('role')
    expect(resolution?.path).toBe('/sys/roles')
    expect(resolution?.name).toBe('SystemRole')
    expect(resolution?.listPreferenceKey).toBe('list.role')
    expect(resolution?.schemeFieldKey).toBe('role')
  })

  it('显式 dataSourceKey 覆盖清单命中值', () => {
    const resolution = resolvePageRoute(
      { ...ROLE_DECL, dataSourceKey: 'user' },
      normalizeFormKeyRecords(FORM_KEYS),
      normalizeDataSourceRecords(DATA_SOURCES),
    )
    expect(resolution?.dataSourceKey).toBe('user')
  })

  it('数据源未登记 / 映射缺失即不可用', () => {
    expect(resolvePageRoute(ROLE_DECL, [], normalizeDataSourceRecords(DATA_SOURCES))).toBeUndefined()
    expect(
      resolvePageRoute({ formKey: 'ghost', title: 'x', path: '/ghost' }, [], normalizeDataSourceRecords(DATA_SOURCES)),
    ).toBeUndefined()
  })
})

describe('BasePageRoute 能力基类', () => {
  it('未注入适配器即占位零请求，resolve 返回 undefined', async () => {
    const route = new PageRoute()
    route.declare(ROLE_DECL)
    await route.load()
    expect(route.requestCount).toBe(0)
    expect(route.degraded).toBe(true)
    expect(route.resolve('role')).toBeUndefined()
  })

  it('声明同键拒重、非法声明丢弃', () => {
    const route = new PageRoute()
    expect(route.declare(ROLE_DECL)).toBe(true)
    expect(route.declare(ROLE_DECL)).toBe(false)
    expect(route.declare({ formKey: 'Bad Key', title: '', path: 'x' } as unknown as FormPageDeclaration)).toBe(false)
    expect(route.declarations()).toHaveLength(1)
  })

  it('装载清单后解析生效（幂等 / 联动键 / 重置）', async () => {
    const route = new PageRoute()
    route.adapter = {
      loadDataSources: async () => DATA_SOURCES,
      loadFormKeys: async () => FORM_KEYS,
    }
    route.declare(ROLE_DECL)
    await route.load()
    expect(route.loaded).toBe(true)
    expect(route.resolve('role')?.dataSourceKey).toBe('role')
    expect(route.dataSourceKeyOf('role')).toBe('role')
    expect(route.listPreferenceKeyOf('role')).toBe('list.role')
    expect(route.schemeFieldKeyOf('role')).toBe('role')
    expect(route.requestCount).toBe(1)
    await route.load()
    expect(route.requestCount).toBe(1)
    route.reset()
    expect(route.loaded).toBe(false)
    expect(route.resolve('role')).toBeUndefined()
  })

  it('装载失败降级但不抛断', async () => {
    const route = new PageRoute()
    route.adapter = { loadFormKeys: async () => Promise.reject(new Error('boom')) }
    await route.load()
    expect(route.loaded).toBe(false)
    expect(route.error).toBe('boom')
  })
})
