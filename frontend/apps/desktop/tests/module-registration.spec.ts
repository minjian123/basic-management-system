// kiwi_id: 976
/** 统一装配通道与模块契约使用用例（10_02 装配 + 01_01 统一装配器收敛；挂载通路为清单驱动远端，见 Kiwi 977 / 978）。 */

import { PLATFORM_SOURCE, assembleRegistrations, releaseRegistrations } from '@bms/core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getModuleLoader, installModules, installPlatformRegistrations, unmountModule } from '@/module/host'
import { PLATFORM_REGISTRATION, bumpRegistriesRevision, registries, registriesRevision } from '@/module/registries'

import { demoDefinition, REMOTE_ENTRY } from './support/module-fixture'

/** Module Federation 运行时替身（远端模块定义经此注入）。 */
const { loadRemote } = vi.hoisted(() => ({ loadRemote: vi.fn() }))
vi.mock('@module-federation/runtime', () => ({ registerRemotes: vi.fn(), loadRemote }))

// 平台内建区域项的组件为重型业务页：此处只核验「懒加载器可解析」，故以轻桩替换，避免拖慢用例。
vi.mock('@/views/system/user/RoleAssignPanel.vue', () => ({ default: { name: 'RoleAssignPanelStub' } }))
vi.mock('@/views/system/role/RoleUsersPanel.vue', () => ({ default: { name: 'RoleUsersPanelStub' } }))

beforeEach(() => {
  loadRemote.mockReset()
  loadRemote.mockResolvedValue({ default: demoDefinition() })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [REMOTE_ENTRY] })),
  )
})

afterEach(() => {
  if (getModuleLoader()?.isMounted('demo') === true) {
    unmountModule('demo')
  }
  vi.unstubAllGlobals()
})

describe('统一装配通道（Kiwi 976）', () => {
  it('平台自身注册走同一入口（平台来源打标；登记键可逆序清理）', () => {
    const keys = installPlatformRegistrations()

    expect(keys).toEqual(['region:sys:user_detail_roles', 'region:sys:role_detail_users'])
    expect(registries.pageArea.get('sys:user_detail_roles')?.registrationSource).toBe(PLATFORM_SOURCE)
    expect(registries.pageArea.get('sys:role_detail_users')?.registrationSource).toBe(PLATFORM_SOURCE)
    expect(PLATFORM_SOURCE).toBe('platform')

    releaseRegistrations(registries, keys)
    expect(registries.pageArea.get('sys:user_detail_roles')).toBeUndefined()
    expect(registries.pageArea.get('sys:role_detail_users')).toBeUndefined()
  })

  it('装配前不可解析、装配后可用、卸载后回到不可解析（八类声明全通道）', async () => {
    expect(registries.component.get('demo:toolbox')).toBeUndefined()
    expect(registries.pageArea.resolveByArea('layout.header')).toEqual([])

    await installModules({})

    expect(registries.component.get('demo:toolbox')).toBeDefined()
    expect(registries.component.get('demo:toolbox')?.registrationSource).toBe('demo')
    expect(registries.fieldRenderer.get('demo:amount')?.fieldType).toBe('amount')
    expect(registries.icon.get('demo:sparkles')).toBeDefined()
    expect(registries.workbenchCard.get('demo:summary')?.title).toBe('模块概览')
    expect(registries.routeMenu.get('DemoHome')?.title).toBe('演示模块')
    expect(registries.pageArea.resolveByArea('layout.header').map((item) => item.key)).toEqual(['demo:hero'])
    expect(registries.themeToken.get('demo:brand')?.mode).toBe('brand')
    expect(registries.i18nPack.byLocale('ZH-CN').map((item) => item.key)).toEqual(['demo:zh-cn'])
    expect(registries.i18nPack.resolve('demo:en')).toMatchObject({ 'demo.title': 'Demo module' })

    unmountModule('demo')

    expect(registries.component.get('demo:toolbox')).toBeUndefined()
    expect(registries.fieldRenderer.get('demo:amount')).toBeUndefined()
    expect(registries.icon.get('demo:sparkles')).toBeUndefined()
    expect(registries.workbenchCard.get('demo:summary')).toBeUndefined()
    expect(registries.routeMenu.get('DemoHome')).toBeUndefined()
    expect(registries.pageArea.resolveByArea('layout.header')).toEqual([])
    expect(registries.themeToken.get('demo:brand')).toBeUndefined()
    expect(registries.i18nPack.byLocale('zh-cn')).toEqual([])
  })

  it('键不属本模块命名空间拒绝（防覆盖平台项）', () => {
    expect(() => assembleRegistrations(registries, 'demo', { components: { 'other:bad': {} } })).toThrow()
    expect(registries.component.get('other:bad')).toBeUndefined()
  })

  it('校验失败零登记；登记键可逆序清理', () => {
    const keys = assembleRegistrations(registries, 'demo', { components: { 'demo:greeting': {} } })
    expect(keys).toEqual(['component:demo:greeting'])
    expect(registries.component.get('demo:greeting')).toBeDefined()
    releaseRegistrations(registries, keys)
    expect(registries.component.get('demo:greeting')).toBeUndefined()

    expect(() =>
      assembleRegistrations(registries, 'demo', {
        components: { 'demo:ok': {} },
        regions: [{ key: 'demo:hero_bad', area: 'layout', component: {} }],
      }),
    ).toThrow()
    expect(registries.component.get('demo:ok')).toBeUndefined()
  })

  it('路由声明登记进路由菜单注册表（无标题不登记）', () => {
    const keys = assembleRegistrations(registries, 'demo', {
      routes: [
        { path: '/demo', name: 'DemoHome', component: async () => ({}), meta: { title: '演示模块' } },
        { path: '/demo/raw', name: 'DemoRaw', component: async () => ({}) },
      ],
    })
    expect(keys).toEqual(['route:DemoHome'])
    expect(registries.routeMenu.get('DemoHome')?.path).toBe('/demo')
    expect(registries.routeMenu.get('DemoRaw')).toBeUndefined()
    releaseRegistrations(registries, keys)
  })

  // kiwi_id: 2238
  it('具名插槽：平台项与模块项同槽、按顺序提示排序、按权限显隐；释放后无残留', () => {
    const platformKeys = installPlatformRegistrations()
    const moduleKeys = assembleRegistrations(registries, 'demo', {
      regions: [
        { key: 'demo:ext', area: 'sys.user.detail.tabs', component: {}, order: 20, title: '用户扩展示例' },
        { key: 'demo:gated', area: 'sys.user.detail.tabs', component: {}, order: 30, title: '受限', perm: 'demo:edit' },
      ],
    })

    const keysOf = (codes: string[]): string[] =>
      registries.pageArea.resolveByArea('sys.user.detail.tabs', { permissionCodes: codes }).map((item) => item.key)

    // 平台内建「角色分配」项带权限码（`user:assign_role`）：无权限码不渲染，与模块项同槽同排序
    expect(keysOf([])).toEqual(['demo:ext'])
    expect(keysOf(['demo:edit', 'user:assign_role'])).toEqual(['sys:user_detail_roles', 'demo:ext', 'demo:gated'])
    expect(registries.pageArea.get('demo:ext')?.title).toBe('用户扩展示例')
    expect(registries.pageArea.get('demo:ext')?.registrationSource).toBe('demo')

    releaseRegistrations(registries, moduleKeys)
    releaseRegistrations(registries, platformKeys)

    expect(registries.pageArea.resolveByArea('sys.user.detail.tabs')).toEqual([])
    expect(registries.pageArea.get('sys:user_detail_roles')).toBeUndefined()
    expect(registries.pageArea.get('demo:ext')).toBeUndefined()
    expect(registries.pageArea.get('demo:gated')).toBeUndefined()
  })
})

// kiwi_id: 976
describe('宿主注册表实例与平台自身声明（Kiwi 976）', () => {
  it('平台声明含两个内建区域项，其组件为可解析的懒加载器（角色分配 / 用户分配）', async () => {
    const declarations = PLATFORM_REGISTRATION.regions ?? []
    expect(declarations.map((item) => item.key)).toEqual(['sys:user_detail_roles', 'sys:role_detail_users'])

    for (const declaration of declarations) {
      const loader = declaration.component as (() => Promise<unknown>) | undefined
      expect(typeof loader).toBe('function')
      await expect(loader?.()).resolves.toBeDefined()
    }
  })

  it('装配版本号自增（注册表实例非响应式，视图据此重算）', () => {
    const before = registriesRevision.value
    bumpRegistriesRevision()
    expect(registriesRevision.value).toBe(before + 1)
    bumpRegistriesRevision()
    expect(registriesRevision.value).toBe(before + 2)
  })
})
