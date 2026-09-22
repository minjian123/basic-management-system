// kiwi_id: 983
/** 样例模块定义用例（模块专属断言：清单身份、八类声明键与路由菜单 meta；通用契约断言见 `module-contract.spec.ts`）。 */

import { describe, expect, it } from 'vitest'

import sampleModule from '../src/index'

describe('样例模块定义（Kiwi 982）', () => {
  it('默认导出模块定义并冻结，清单名 / 版本 / 契约版本齐备（版本构建期注入）', () => {
    expect(sampleModule.manifest.name).toBe('sample')
    expect(sampleModule.manifest.version).toMatch(/^\d+\.\d+\.\d+$/)
    expect(Number.isInteger(sampleModule.manifest.contractVersion)).toBe(true)
    expect(Object.isFrozen(sampleModule)).toBe(true)
  })

  it('八类声明键均为模块专属值且带 sample: 命名空间前缀', () => {
    const registration = sampleModule.setup({})

    expect(registration.routes?.map((item) => item.name)).toEqual(['SampleList', 'SampleDetail', 'SampleForm'])
    expect(Object.keys(registration.components ?? {})).toEqual(['sample:priority-tag'])
    expect(registration.fieldRenderers?.map((item) => item.key)).toEqual(['sample:priority'])
    expect(Object.keys(registration.icons ?? {})).toEqual(['sample:record'])
    expect((registration.cards?.[0] as { key: string }).key).toBe('sample:summary')
    expect(registration.regions?.map((item) => item.key)).toEqual(['sample:header-badge'])
    expect(registration.themeTokens?.map((item) => item.key)).toEqual(['sample:accent'])
    expect(registration.i18nPacks?.map((item) => item.key)).toEqual(['sample:zh-cn', 'sample:en'])
  })

  it('路由菜单 meta：列表进菜单并归组、详情 / 表单不进菜单（menu:false）', () => {
    const registration = sampleModule.setup({})
    const routes = registration.routes ?? []
    const list = routes.find((item) => item.name === 'SampleList')
    const detail = routes.find((item) => item.name === 'SampleDetail')
    const form = routes.find((item) => item.name === 'SampleForm')

    expect(list?.path).toBe('/sample')
    expect(list?.meta?.group).toBe('示例模块')
    expect(list?.meta?.menu).not.toBe(false)
    expect(detail?.meta?.menu).toBe(false)
    expect(form?.meta?.menu).toBe(false)
    expect(routes.every((item) => typeof item.component === 'function')).toBe(true)
  })

  it('模块自有令牌以 --bms-* 命名（不覆盖宿主核心令牌）', () => {
    const registration = sampleModule.setup({})
    const token = registration.themeTokens?.[0]
    expect(Object.keys(token?.tokens ?? {})).toEqual(['--bms-sample-accent'])
  })
})
