// kiwi_id: 976
/** 扩展点注册表用例（10_02 五类最小实现 + 01_01 补齐八类与统一装配）。 */

import { describe, expect, it, vi } from 'vitest'

import {
  BaseError,
  BaseProviderRegistry,
  ComponentProvider,
  FieldRendererProvider,
  I18nPackProvider,
  IconProvider,
  PageAreaProvider,
  RouteMenuProvider,
  ThemeTokenProvider,
  WorkbenchCardProvider,
  createRegistries,
  type DuplicatePolicy,
} from '../src'

/** 宽和档注册表（fixture：验证「告警保留首个」能力）。 */
class LenientRegistry extends BaseProviderRegistry<string> {
  readonly pluginKey = 'lenient-registry'
  readonly pluginName = 'core'

  override get duplicatePolicy(): DuplicatePolicy {
    return 'lenient'
  }

  protected providerKey(provider: string): string {
    return provider
  }
}

/**
 * 八类注册表公共契约断言（同一套断言覆盖各域）。
 *
 * @param registry 目标注册表。
 * @param make 以键构造注册项。
 * @param keyA 首个键。
 * @param keyB 第二个键。
 */
function assertRegistryContract(
  registry: BaseProviderRegistry<{ key: string }>,
  make: (key: string) => { key: string },
  keyA: string,
  keyB: string,
): void {
  expect(registry.get(keyA)).toBeUndefined()
  registry.register(make(keyA))
  registry.register(make(keyB))
  expect(registry.get(keyA)?.key).toBe(keyA)
  expect(registry.keys()).toEqual([keyA, keyB])
  expect([...registry.snapshot().keys()]).toEqual([keyA, keyB])
  expect(() => registry.register(make(keyA))).toThrow(BaseError)
  expect(registry.get('missing:key')).toBeUndefined()
  expect(registry.unregister(keyA)).toBe(true)
  expect(registry.unregister(keyA)).toBe(false)
  expect(registry.keys()).toEqual([keyB])
}

describe('八类注册表公共契约（Kiwi 976）', () => {
  it('登记 / 解析 / 拒重 / 未命中 / 保序 / 只读快照覆盖八域', () => {
    const registries = createRegistries()
    assertRegistryContract(
      registries.routeMenu,
      (key) => new RouteMenuProvider(key, '/contract', '契约'),
      'ContractHome',
      'ContractToolbox',
    )
    assertRegistryContract(
      registries.pageArea,
      (key) => new PageAreaProvider(key, 'layout.header', {}),
      'platform:hero',
      'platform:footer',
    )
    assertRegistryContract(
      registries.component,
      (key) => new ComponentProvider(key, {}),
      'platform:card-a',
      'platform:card-b',
    )
    assertRegistryContract(
      registries.fieldRenderer,
      (key) => new FieldRendererProvider(key, {}),
      'platform:amount',
      'platform:text',
    )
    assertRegistryContract(registries.icon, (key) => new IconProvider(key, {}), 'el:User', 'el:Menu')
    assertRegistryContract(
      registries.workbenchCard,
      (key) => new WorkbenchCardProvider(key, {}),
      'platform:summary',
      'platform:detail',
    )
    assertRegistryContract(
      registries.themeToken,
      (key) => new ThemeTokenProvider(key, {}),
      'platform:default',
      'platform:dark',
    )
    assertRegistryContract(registries.i18nPack, (key) => new I18nPackProvider(key, {}), 'platform:zh-cn', 'platform:en')
  })
})

describe('createRegistries', () => {
  it('产出八类注册表并与平台自身注册共用', () => {
    const registries = createRegistries()
    expect(Object.keys(registries)).toEqual([
      'routeMenu',
      'pageArea',
      'component',
      'fieldRenderer',
      'icon',
      'workbenchCard',
      'themeToken',
      'i18nPack',
    ])
  })
})

describe('RouteMenuRegistry', () => {
  it('登记 / 保序 / 只读快照 / 重复拒重', () => {
    const registries = createRegistries()
    registries.routeMenu.register(new RouteMenuProvider('DemoHome', '/demo', '演示模块'))
    registries.routeMenu.register(new RouteMenuProvider('DemoToolbox', '/demo/toolbox', '工具', 'sparkles'))

    expect(registries.routeMenu.keys()).toEqual(['DemoHome', 'DemoToolbox'])
    expect(registries.routeMenu.get('DemoHome')?.path).toBe('/demo')
    expect(registries.routeMenu.snapshot().get('DemoHome')?.path).toBe('/demo')
    expect(() => registries.routeMenu.register(new RouteMenuProvider('DemoHome', '/other', '重复'))).toThrow(BaseError)

    expect(registries.routeMenu.unregister('DemoHome')).toBe(true)
    expect(registries.routeMenu.unregister('DemoHome')).toBe(false)
    expect(registries.routeMenu.keys()).toEqual(['DemoToolbox'])
  })

  it('路径不以 / 开头拒绝', () => {
    const registries = createRegistries()
    expect(() => registries.routeMenu.register(new RouteMenuProvider('Bad', 'demo', '坏路径'))).toThrow(BaseError)
  })
})

describe('命名空间键校验', () => {
  it('八类中命名空间键域均拒绝无命名空间键', () => {
    const registries = createRegistries()
    registries.component.register(new ComponentProvider('demo:greeting', {}))
    registries.icon.register(new IconProvider('demo:sparkles', 'sparkles'))
    registries.workbenchCard.register(new WorkbenchCardProvider('demo:summary', {}, '概览'))
    registries.pageArea.register(new PageAreaProvider('demo:hero', 'layout.header', {}))
    registries.themeToken.register(new ThemeTokenProvider('demo:brand', {}, 'brand'))
    registries.i18nPack.register(new I18nPackProvider('demo:zh-cn', {}))

    expect(registries.component.get('demo:greeting')).toBeDefined()
    expect(registries.icon.keys()).toEqual(['demo:sparkles'])
    expect(registries.workbenchCard.get('demo:summary')?.title).toBe('概览')
    expect(registries.pageArea.get('demo:hero')?.area).toBe('layout.header')
    expect(registries.themeToken.get('demo:brand')?.mode).toBe('brand')
    expect(registries.i18nPack.get('demo:zh-cn')?.locale).toBe('zh-cn')

    expect(() => registries.component.register(new ComponentProvider('noNamespace', {}))).toThrow(BaseError)
    expect(() => registries.icon.register(new IconProvider('demo', {}))).toThrow(BaseError)
    expect(() => registries.workbenchCard.register(new WorkbenchCardProvider('demo:', {}))).toThrow(BaseError)
    expect(() => registries.pageArea.register(new PageAreaProvider('noNamespace', 'layout.header', {}))).toThrow(
      BaseError,
    )
    expect(() => registries.themeToken.register(new ThemeTokenProvider('noNamespace', {}))).toThrow(BaseError)
    expect(() => registries.i18nPack.register(new I18nPackProvider('noNamespace', {}))).toThrow(BaseError)
  })
})

describe('PageAreaRegistry', () => {
  it('按区域标识解析（保序 / 未知区域空数组 / 区域去重）', () => {
    const registries = createRegistries()
    registries.pageArea.register(new PageAreaProvider('demo:hero', 'layout.header', {}, 10))
    registries.pageArea.register(new PageAreaProvider('demo:notice', 'layout.header', {}, 5))
    registries.pageArea.register(new PageAreaProvider('demo:foot', 'layout.footer', {}))

    expect(registries.pageArea.resolveByArea('layout.header').map((item) => item.key)).toEqual([
      'demo:hero',
      'demo:notice',
    ])
    expect(registries.pageArea.resolveByArea('layout.footer').map((item) => item.key)).toEqual(['demo:foot'])
    expect(registries.pageArea.resolveByArea('layout.missing')).toEqual([])
    expect(registries.pageArea.areas()).toEqual(['layout.header', 'layout.footer'])
    expect(registries.pageArea.get('demo:hero')?.order).toBe(10)
  })

  it('区域标识须为点分标识', () => {
    const registries = createRegistries()
    expect(() => registries.pageArea.register(new PageAreaProvider('demo:hero', 'layout', {}))).toThrow(BaseError)
    expect(() => registries.pageArea.register(new PageAreaProvider('demo:hero', 'Layout.Header', {}))).toThrow(
      BaseError,
    )
  })
})

describe('ThemeTokenRegistry', () => {
  it('解析令牌映射 / 按模式筛选（空串返回全部）', () => {
    const registries = createRegistries()
    registries.themeToken.register(
      new ThemeTokenProvider('platform:default', { '--bms-color-primary': '#1677ff' }, 'light'),
    )
    registries.themeToken.register(new ThemeTokenProvider('tenant:acme', { '--bms-color-primary': '#3a7bd5' }, 'brand'))

    expect(registries.themeToken.resolve('platform:default')).toEqual({ '--bms-color-primary': '#1677ff' })
    expect(registries.themeToken.resolve('missing:default')).toBeUndefined()
    expect(registries.themeToken.byMode('brand').map((item) => item.key)).toEqual(['tenant:acme'])
    expect(registries.themeToken.byMode('')).toHaveLength(2)
    expect(registries.themeToken.byMode('dark')).toEqual([])
  })
})

describe('I18nPackRegistry', () => {
  it('解析文案包 / 按语言解析（入参小写归一）', () => {
    const registries = createRegistries()
    registries.i18nPack.register(new I18nPackProvider('demo:zh-cn', { 'demo.title': '演示模块' }))
    registries.i18nPack.register(new I18nPackProvider('demo:en', { 'demo.title': 'Demo module' }))

    expect(registries.i18nPack.resolve('demo:zh-cn')).toEqual({ 'demo.title': '演示模块' })
    expect(registries.i18nPack.resolve('demo:ja')).toBeUndefined()
    expect(registries.i18nPack.byLocale('ZH-CN').map((item) => item.key)).toEqual(['demo:zh-cn'])
    expect(registries.i18nPack.byLocale('ja')).toEqual([])
    expect(registries.i18nPack.get('demo:en')?.locale).toBe('en')
  })

  it('语言标识须小写归一且合法', () => {
    const registries = createRegistries()
    expect(() => registries.i18nPack.register(new I18nPackProvider('demo:ZH-CN', {}))).toThrow(BaseError)
    expect(() => registries.i18nPack.register(new I18nPackProvider('demo:x', {}))).toThrow(BaseError)
  })
})

describe('FieldRendererRegistry', () => {
  it('按类型解析首个命中', () => {
    const registries = createRegistries()
    registries.fieldRenderer.register(new FieldRendererProvider('demo:amount', {}, 'amount'))
    registries.fieldRenderer.register(new FieldRendererProvider('demo:text', {}))

    expect(registries.fieldRenderer.resolveByType('amount')?.key).toBe('demo:amount')
    expect(registries.fieldRenderer.resolveByType('missing')).toBeUndefined()
    expect(registries.fieldRenderer.get('missing')).toBeUndefined()
  })
})

describe('IconRegistry icon key 扩展（08_02）', () => {
  it('接受 icon key（大小写 / 数字段）并拒绝非法与重复', () => {
    const registries = createRegistries()
    registries.icon.register(new IconProvider('el:User', {}, { name: 'User', category: 'common' }))
    registries.icon.register(new IconProvider('biz:purchase-order', {}))
    registries.icon.register(new IconProvider('custom:1024', {}))

    expect(registries.icon.keys()).toEqual(['el:User', 'biz:purchase-order', 'custom:1024'])
    expect(() => registries.icon.register(new IconProvider('noPrefix', {}))).toThrow(BaseError)
    expect(() => registries.icon.register(new IconProvider('el:User', {}))).toThrow(BaseError)
  })

  it('来源前缀、检索与解析', () => {
    const registries = createRegistries()
    registries.icon.register(new IconProvider('el:User', {}, { name: 'User', category: 'common', tags: ['用户'] }))
    registries.icon.register(new IconProvider('biz:PurchaseOrder', {}, { name: '采购单' }))

    expect(registries.icon.byPrefix('el').map((item) => item.key)).toEqual(['el:User'])
    expect(registries.icon.byPrefix('biz:').map((item) => item.key)).toEqual(['biz:PurchaseOrder'])
    expect(registries.icon.search('user').map((item) => item.key)).toEqual(['el:User'])
    expect(registries.icon.search('采购').map((item) => item.key)).toEqual(['biz:PurchaseOrder'])
    expect(registries.icon.search('')).toHaveLength(2)
    expect(registries.icon.resolve('el:User')).toBeDefined()
    expect(registries.icon.resolve('el:Missing')).toBeUndefined()
  })
})

describe('注册表基座拒重档位', () => {
  it('严格档（缺省）同键抛错', () => {
    const registries = createRegistries()
    registries.component.register(new ComponentProvider('demo:a', {}))
    expect(registries.component.duplicatePolicy).toBe('strict')
    expect(() => registries.component.register(new ComponentProvider('demo:a', {}))).toThrow(BaseError)
  })

  it('宽和档同键告警保留首个', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const registry = new LenientRegistry()
    registry.register('a')
    registry.register('a')
    expect(registry.keys()).toEqual(['a'])
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})
