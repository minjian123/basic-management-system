/** 模块注册装配与样式作用域护栏用例（10_02）。 */

import { ComponentProvider, IconProvider, WorkbenchCardProvider } from '@bms/core'
import { afterEach, describe, expect, it } from 'vitest'

import { applyModuleRegistration, registries, removeRegistration } from '@/module/registries'
import { getModuleLoader, mountModule, unmountModule } from '@/module/host'
import { demoModule } from '@/modules/demo'

afterEach(() => {
  if (getModuleLoader().isMounted('demo')) {
    unmountModule('demo')
  }
})

describe('applyModuleRegistration', () => {
  it('逐项倒入注册表并可按键解析', () => {
    const keys = applyModuleRegistration('demo', {
      components: { 'demo:greeting': {} },
      icons: { 'demo:sparkles': 'sparkles' },
      cards: [new WorkbenchCardProvider('demo:summary', {}, '概览')],
    })
    expect(keys).toEqual(['component:demo:greeting', 'icon:demo:sparkles', 'card:demo:summary'])
    expect(registries.component.get('demo:greeting')).toBeDefined()
    expect(registries.icon.get('demo:sparkles')).toBeDefined()
    expect(registries.workbenchCard.get('demo:summary')?.title).toBe('概览')

    removeRegistration(keys)
    expect(registries.component.get('demo:greeting')).toBeUndefined()
  })

  it('键不属本模块命名空间拒绝', () => {
    expect(() => applyModuleRegistration('demo', { components: { 'other:bad': {} } })).toThrow()
    expect(() => applyModuleRegistration('demo', { cards: [new WorkbenchCardProvider('demo:x', {})] })).not.toThrow()
  })

  it('路由声明登记进路由菜单注册表（无标题不登记）', () => {
    applyModuleRegistration('demo', {
      routes: [
        { path: '/demo', name: 'DemoHome', component: async () => ({}), meta: { title: '演示模块' } },
        { path: '/demo/raw', name: 'DemoRaw', component: async () => ({}) },
      ],
    })
    expect(registries.routeMenu.get('DemoHome')?.path).toBe('/demo')
    expect(registries.routeMenu.get('DemoRaw')).toBeUndefined()
    registries.routeMenu.unregister('DemoHome')
  })
})

describe('演示模块契约使用', () => {
  it('挂载后组件 / 图标 / 卡片 / 路由菜单均已登记，卸载后清理', async () => {
    await mountModule('demo', {})
    expect(registries.component.get('demo:toolbox')).toBeDefined()
    expect(registries.icon.get('demo:sparkles')).toBeDefined()
    expect(registries.workbenchCard.get('demo:summary')?.title).toBe('模块概览')
    expect(registries.routeMenu.get('DemoHome')?.title).toBe('演示模块')

    unmountModule('demo')
    expect(registries.component.get('demo:toolbox')).toBeUndefined()
    expect(registries.icon.get('demo:sparkles')).toBeUndefined()
    expect(registries.workbenchCard.get('demo:summary')).toBeUndefined()
    expect(registries.routeMenu.get('DemoHome')).toBeUndefined()
  })

  it('模块定义校验通过并声明版本', () => {
    expect(demoModule.manifest).toMatchObject({ name: 'demo', version: '0.1.0' })
    expect(new ComponentProvider('x:y', {})).toBeDefined()
    expect(new IconProvider('x:y', {})).toBeDefined()
  })
})
