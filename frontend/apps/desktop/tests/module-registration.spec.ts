// kiwi_id: 976
/** 统一装配通道与模块契约使用用例（10_02 装配 + 01_01 统一装配器收敛；挂载通路为清单驱动远端，见 Kiwi 977 / 978）。 */

import { PLATFORM_SOURCE, assembleRegistrations, releaseRegistrations } from '@bms/core'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getModuleLoader, installModules, installPlatformRegistrations, unmountModule } from '@/module/host'
import { registries } from '@/module/registries'

import { demoDefinition, REMOTE_ENTRY } from './support/module-fixture'

/** Module Federation 运行时替身（远端模块定义经此注入）。 */
const { loadRemote } = vi.hoisted(() => ({ loadRemote: vi.fn() }))
vi.mock('@module-federation/runtime', () => ({ registerRemotes: vi.fn(), loadRemote }))

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
  it('平台自身注册走同一入口（空声明不产生登记）', () => {
    expect(installPlatformRegistrations()).toEqual([])
    expect(PLATFORM_SOURCE).toBe('platform')
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
        regions: [{ key: 'demo:hero-bad', area: 'layout', component: {} }],
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
})
