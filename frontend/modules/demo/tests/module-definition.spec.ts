// kiwi_id: 978
/** 演示模块定义契约用例（远端独立构建：默认导出、清单一致、八类声明与页面懒加载）。 */

import { describe, expect, it } from 'vitest'

import demoModule from '../src/index'

describe('演示模块定义（Kiwi 978）', () => {
  it('默认导出模块定义并冻结，清单名与版本与宿主清单条目一致', () => {
    expect(demoModule.manifest).toEqual({ name: 'demo', version: '0.1.0' })
    expect(Object.isFrozen(demoModule)).toBe(true)
  })

  it('路由一律懒加载（页面独立分包、不进容器入口），路径以 / 开头且有标题', () => {
    const routes = demoModule.setup({}).routes ?? []

    expect(routes.length).toBeGreaterThanOrEqual(2)
    for (const route of routes) {
      expect(typeof route.component).toBe('function')
      expect(route.path.startsWith('/')).toBe(true)
      expect(route.meta?.title).toBeTruthy()
    }
  })

  it('八类声明通道齐全且键带模块命名空间前缀', () => {
    const registration = demoModule.setup({})

    expect(registration.routes?.map((item) => item.name)).toEqual(['DemoHome', 'DemoToolbox'])
    expect(Object.keys(registration.components ?? {})).toEqual(['demo:toolbox'])
    expect(registration.fieldRenderers?.map((item) => item.key)).toEqual(['demo:amount'])
    expect(Object.keys(registration.icons ?? {})).toEqual(['demo:sparkles'])
    expect(registration.cards?.length).toBe(1)
    expect(registration.regions?.map((item) => item.key)).toEqual(['demo:hero'])
    expect(registration.themeTokens?.map((item) => item.key)).toEqual(['demo:brand'])
    expect(registration.i18nPacks?.map((item) => item.key)).toEqual(['demo:zh-cn', 'demo:en'])

    const namespaced = [
      ...Object.keys(registration.components ?? {}),
      ...(registration.fieldRenderers ?? []).map((item) => item.key),
      ...Object.keys(registration.icons ?? {}),
      ...(registration.regions ?? []).map((item) => item.key),
      ...(registration.themeTokens ?? []).map((item) => item.key),
      ...(registration.i18nPacks ?? []).map((item) => item.key),
    ]
    for (const key of namespaced) {
      expect(key.startsWith('demo:')).toBe(true)
    }
  })

  it('区域标识为点分格式、文案包语言标识小写、令牌使用 --bms-* 变量', () => {
    const registration = demoModule.setup({})

    for (const region of registration.regions ?? []) {
      expect(region.area).toMatch(/^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$/)
      expect(typeof region.component).toBe('function')
    }
    for (const pack of registration.i18nPacks ?? []) {
      expect(pack.key.split(':')[1]).toBe(pack.key.split(':')[1]?.toLowerCase())
    }
    for (const token of registration.themeTokens ?? []) {
      for (const name of Object.keys(token.tokens)) {
        expect(name.startsWith('--bms-')).toBe(true)
      }
    }
  })
})
