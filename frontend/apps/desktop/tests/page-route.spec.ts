// kiwi_id: 2291
/**
 * 通用页面路由接线用例（02_13）：表单页路由统一装载 / 卸载（幂等）+ 按 form_key 解析页面。
 */

import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'

import {
  FORM_PAGE_DECLARATIONS,
  ensureFormPageRoutes,
  pageRoute,
  resolvePageRoute,
  uninstallFormPageRoutes,
} from '@/router/page-route'

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
  ],
}

const FORM_KEYS = {
  items: [
    { form_key: 'role', name: '角色', kind: 'dict', table: 'sys_role', data_source_key: 'role', status: 'enabled' },
  ],
}

/** 路由实例（用例自持）。 */
let router: Router

beforeEach(() => {
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  uninstallFormPageRoutes(router)
  pageRoute.reset()
})

describe('表单页路由统一装载（02_13）', () => {
  it('装载表单页路由并按名卸载（幂等；跳过已存在路径）', () => {
    const names = ensureFormPageRoutes(router)
    expect(names).toEqual(['SystemRole', 'SystemUser', 'SystemTenant', 'SystemMenu', 'SystemForm'])
    expect(router.hasRoute('SystemRole')).toBe(true)
    expect(router.hasRoute('SystemUser')).toBe(true)
    // 幂等：再次装载不重复
    expect(ensureFormPageRoutes(router)).toEqual(names)
    uninstallFormPageRoutes(router)
    expect(router.hasRoute('SystemRole')).toBe(false)
    // 卸载后再卸载（空清单）为幂等空操作
    uninstallFormPageRoutes(router)
    expect(router.hasRoute('SystemRole')).toBe(false)
  })

  it('已存在同路径静态路由时跳过（不覆盖）', () => {
    router.addRoute({ path: '/sys/roles', name: 'PreExisting', component: { template: '<div />' } })
    const names = ensureFormPageRoutes(router)
    expect(names).toEqual(['SystemUser', 'SystemTenant', 'SystemMenu', 'SystemForm'])
    expect(router.hasRoute('PreExisting')).toBe(true)
  })

  it('平台表单页声明覆盖 role / user 且标题取自声明', () => {
    expect(FORM_PAGE_DECLARATIONS.map((item) => item.formKey)).toEqual(['role', 'user', 'tenant', 'menu', 'form'])
    expect(resolvePageRoute('role')).toBeUndefined()
    expect(pageRoute.listPreferenceKeyOf('role')).toBe('list.role')
    expect(pageRoute.schemeFieldKeyOf('role')).toBe('role')
    expect(pageRoute.declarationOf('user')?.title).toBe('用户管理')
  })
})

describe('按 form_key 解析页面（02_13）', () => {
  it('装载清单后解析路由 / 数据源 / 联动键', async () => {
    pageRoute.adapter = {
      loadDataSources: async () => DATA_SOURCES,
      loadFormKeys: async () => FORM_KEYS,
    }
    await pageRoute.load()
    const resolution = pageRoute.resolve('role')
    expect(resolution?.dataSourceKey).toBe('role')
    expect(resolution?.path).toBe('/sys/roles')
    expect(resolution?.listPreferenceKey).toBe('list.role')
    expect(resolution?.schemeFieldKey).toBe('role')
  })

  it('未装载清单（数据源未登记）即不可用', async () => {
    pageRoute.adapter = undefined
    await pageRoute.load()
    expect(pageRoute.resolve('role')).toBeUndefined()
  })
})
