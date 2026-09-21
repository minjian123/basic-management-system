// kiwi_id: 976
/** 统一装配器用例（平台自身注册与模块注册共用同一通道）。 */

import { describe, expect, it } from 'vitest'

import {
  BaseError,
  ComponentProvider,
  PLATFORM_SOURCE,
  WorkbenchCardProvider,
  assembleRegistrations,
  createRegistries,
  releaseRegistrations,
} from '../src'

describe('assembleRegistrations（Kiwi 976）', () => {
  it('平台自身注册：不强制模块前缀，来源打标为 platform', () => {
    const registries = createRegistries()
    const keys = assembleRegistrations(registries, PLATFORM_SOURCE, {
      components: { 'layout:header-actions': {} },
      icons: { 'platform:sparkles': 'sparkles' },
      cards: [new WorkbenchCardProvider('platform:summary', {}, '概览')],
      regions: [{ key: 'layout:hero', area: 'layout.header', component: {} }],
      themeTokens: [{ key: 'platform:default', tokens: { '--bms-color-primary': '#1677ff' }, mode: 'light' }],
      i18nPacks: [{ key: 'platform:zh-cn', messages: { 'common.ok': '确定' } }],
    })

    expect(keys).toEqual([
      'component:layout:header-actions',
      'icon:platform:sparkles',
      'card:platform:summary',
      'region:layout:hero',
      'themeToken:platform:default',
      'i18nPack:platform:zh-cn',
    ])
    expect(registries.component.get('layout:header-actions')?.registrationSource).toBe(PLATFORM_SOURCE)
    expect(registries.pageArea.resolveByArea('layout.header').map((item) => item.key)).toEqual(['layout:hero'])
    expect(registries.themeToken.resolve('platform:default')).toEqual({ '--bms-color-primary': '#1677ff' })
    expect(registries.i18nPack.byLocale('zh-CN').map((item) => item.key)).toEqual(['platform:zh-cn'])
  })

  it('模块注册：键须以模块名为命名空间，越权拒绝', () => {
    const registries = createRegistries()
    expect(() => assembleRegistrations(registries, 'demo', { components: { 'other:bad': {} } })).toThrow(BaseError)
    expect(() =>
      assembleRegistrations(registries, 'demo', {
        regions: [{ key: 'other:hero', area: 'layout.header', component: {} }],
      }),
    ).toThrow(BaseError)
    expect(registries.component.get('other:bad')).toBeUndefined()
  })

  it('模块注册：八类声明逐项倒入并打标', () => {
    const registries = createRegistries()
    assembleRegistrations(registries, 'demo', {
      routes: [{ path: '/demo', name: 'DemoHome', component: async () => ({}), meta: { title: '演示模块' } }],
      components: { 'demo:toolbox': {} },
      icons: { 'demo:sparkles': 'sparkles' },
      cards: [new WorkbenchCardProvider('demo:summary', {}, '模块概览')],
      regions: [{ key: 'demo:hero', area: 'layout.header', component: {} }],
      themeTokens: [{ key: 'demo:brand', tokens: { '--bms-color-primary': '#3a7bd5' }, mode: 'brand' }],
      i18nPacks: [{ key: 'demo:zh-cn', messages: { 'demo.title': '演示模块' } }],
    })

    expect(registries.component.get('demo:toolbox')?.registrationSource).toBe('demo')
    expect(registries.icon.get('demo:sparkles')).toBeDefined()
    expect(registries.workbenchCard.get('demo:summary')?.title).toBe('模块概览')
    expect(registries.routeMenu.get('DemoHome')?.path).toBe('/demo')
    expect(registries.routeMenu.get('DemoHome')?.registrationSource).toBe('demo')
    expect(registries.pageArea.get('demo:hero')?.area).toBe('layout.header')
    expect(registries.themeToken.get('demo:brand')?.mode).toBe('brand')
    expect(registries.i18nPack.get('demo:zh-cn')?.locale).toBe('zh-cn')
  })

  it('两段式：校验阶段失败不产生任何登记', () => {
    const registries = createRegistries()
    expect(() =>
      assembleRegistrations(registries, 'demo', {
        components: { 'demo:ok': {} },
        regions: [{ key: 'demo:hero', area: 'layout', component: {} }],
      }),
    ).toThrow(BaseError)
    expect(registries.component.keys()).toEqual([])
    expect(registries.pageArea.keys()).toEqual([])
  })

  it('两段式：倒入途中冲突回滚本次已登记项', () => {
    const registries = createRegistries()
    registries.component.register(new ComponentProvider('demo:existing', {}))
    expect(() =>
      assembleRegistrations(registries, 'demo', { components: { 'demo:ok': {}, 'demo:existing': {} } }),
    ).toThrow(BaseError)

    expect(registries.component.get('demo:ok')).toBeUndefined()
    expect(registries.component.get('demo:existing')).toBeDefined()
    expect(registries.component.keys()).toEqual(['demo:existing'])
  })

  it('路由：无 meta.title 不登记；路径非 / 开头抛错', () => {
    const registries = createRegistries()
    assembleRegistrations(registries, 'demo', {
      routes: [
        { path: '/demo/raw', name: 'DemoRaw', component: async () => ({}) },
        { path: '/demo', name: 'DemoHome', component: async () => ({}), meta: { title: '演示模块' } },
      ],
    })
    expect(registries.routeMenu.get('DemoRaw')).toBeUndefined()
    expect(registries.routeMenu.get('DemoHome')?.title).toBe('演示模块')

    expect(() =>
      assembleRegistrations(registries, 'demo', {
        routes: [{ path: 'demo/bad', name: 'DemoBad', component: async () => ({}), meta: { title: '坏路径' } }],
      }),
    ).toThrow(BaseError)
  })
})

describe('releaseRegistrations', () => {
  it('按登记键清理（幂等）', () => {
    const registries = createRegistries()
    const keys = assembleRegistrations(registries, 'demo', {
      components: { 'demo:toolbox': {} },
      icons: { 'demo:sparkles': 'sparkles' },
      cards: [new WorkbenchCardProvider('demo:summary', {}, '模块概览')],
      regions: [{ key: 'demo:hero', area: 'layout.header', component: {} }],
      themeTokens: [{ key: 'demo:brand', tokens: {} }],
      i18nPacks: [{ key: 'demo:zh-cn', messages: {} }],
      routes: [{ path: '/demo', name: 'DemoHome', component: async () => ({}), meta: { title: '演示模块' } }],
    })

    releaseRegistrations(registries, keys)
    releaseRegistrations(registries, keys)

    expect(registries.component.get('demo:toolbox')).toBeUndefined()
    expect(registries.icon.get('demo:sparkles')).toBeUndefined()
    expect(registries.workbenchCard.get('demo:summary')).toBeUndefined()
    expect(registries.pageArea.get('demo:hero')).toBeUndefined()
    expect(registries.themeToken.get('demo:brand')).toBeUndefined()
    expect(registries.i18nPack.get('demo:zh-cn')).toBeUndefined()
    expect(registries.routeMenu.get('DemoHome')).toBeUndefined()
  })

  it('未知分组键跳过不抛错', () => {
    const registries = createRegistries()
    expect(() => releaseRegistrations(registries, ['unknown:demo:x', 'component:demo:missing'])).not.toThrow()
  })
})
