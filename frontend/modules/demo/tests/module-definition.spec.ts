// kiwi_id: 978
/** 演示模块定义用例（模块专属断言：清单身份与具体声明键；通用契约断言见 `module-contract.spec.ts` 的同一套断言）。 */

import { describe, expect, it } from 'vitest'

import demoModule from '../src/index'

describe('演示模块定义（Kiwi 978）', () => {
  it('默认导出模块定义并冻结，清单名 / 版本 / 契约版本齐备（版本构建期注入）', () => {
    expect(demoModule.manifest.name).toBe('demo')
    expect(demoModule.manifest.version).toMatch(/^\d+\.\d+\.\d+$/)
    expect(Number.isInteger(demoModule.manifest.contractVersion)).toBe(true)
    expect(Object.isFrozen(demoModule)).toBe(true)
  })

  it('演示路由与声明键为模块专属值（键规则见契约用例）', () => {
    const registration = demoModule.setup({})

    expect(registration.routes?.map((item) => item.name)).toEqual(['DemoHome', 'DemoToolbox'])
    expect(Object.keys(registration.components ?? {})).toEqual(['demo:toolbox'])
    expect(registration.fieldRenderers?.map((item) => item.key)).toEqual(['demo:amount'])
    expect(Object.keys(registration.icons ?? {})).toEqual(['demo:sparkles'])
    expect(registration.cards?.length).toBe(1)
    expect(registration.regions?.map((item) => item.key)).toEqual(['demo:hero'])
    expect(registration.themeTokens?.map((item) => item.key)).toEqual(['demo:brand'])
    expect(registration.i18nPacks?.map((item) => item.key)).toEqual(['demo:zh-cn', 'demo:en'])
  })
})
