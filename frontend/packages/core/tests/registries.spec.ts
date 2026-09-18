/** 扩展点注册表用例（10_02）。 */

import { describe, expect, it } from 'vitest'

import {
  BaseError,
  ComponentProvider,
  FieldRendererProvider,
  IconProvider,
  RouteMenuProvider,
  WorkbenchCardProvider,
  createRegistries,
} from '../src'

describe('createRegistries', () => {
  it('产出五个注册表并与平台自身注册共用', () => {
    const registries = createRegistries()
    expect(Object.keys(registries)).toEqual(['routeMenu', 'component', 'fieldRenderer', 'icon', 'workbenchCard'])
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
  it('组件 / 图标 / 卡片键须为命名空间键', () => {
    const registries = createRegistries()
    registries.component.register(new ComponentProvider('demo:greeting', {}))
    registries.icon.register(new IconProvider('demo:sparkles', 'sparkles'))
    registries.workbenchCard.register(new WorkbenchCardProvider('demo:summary', {}, '概览'))

    expect(registries.component.get('demo:greeting')).toBeDefined()
    expect(registries.icon.keys()).toEqual(['demo:sparkles'])
    expect(registries.workbenchCard.get('demo:summary')?.title).toBe('概览')

    expect(() => registries.component.register(new ComponentProvider('noNamespace', {}))).toThrow(BaseError)
    expect(() => registries.icon.register(new IconProvider('demo', {}))).toThrow(BaseError)
    expect(() => registries.workbenchCard.register(new WorkbenchCardProvider('demo:', {}))).toThrow(BaseError)
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
