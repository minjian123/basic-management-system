// kiwi_id: 2238
/** 模块定义用例（模块专属断言：清单身份、具名插槽区域项声明与命名口径；通用契约断言见 `module-contract.spec.ts`）。 */

import { NAMED_SLOT_ID_PATTERN } from '@bms/core'
import { describe, expect, it } from 'vitest'

import slotSampleModule, { USER_DETAIL_TABS_SLOT, USER_EXTENSION_UPDATE_PERMISSION } from '../src/index'

describe('具名插槽样例插件定义（Kiwi 2238）', () => {
  it('默认导出模块定义并冻结，清单名 / 版本 / 契约版本齐备（版本构建期注入）', () => {
    expect(slotSampleModule.manifest.name).toBe('slot-sample')
    expect(slotSampleModule.manifest.version).toMatch(/^\d+\.\d+\.\d+$/)
    expect(Number.isInteger(slotSampleModule.manifest.contractVersion)).toBe(true)
    expect(Object.isFrozen(slotSampleModule)).toBe(true)
  })

  it('不声明路由（无页面、不进菜单），只声明具名插槽区域项与文案包', () => {
    const registration = slotSampleModule.setup({})

    expect(registration.routes).toBeUndefined()
    expect(registration.regions?.map((item) => item.key)).toEqual([
      'slot-sample:user-extension',
      'slot-sample:user-extension-detail',
    ])
    expect(registration.i18nPacks?.map((item) => item.key)).toEqual(['slot-sample:zh-cn', 'slot-sample:en'])
  })

  it('具名插槽标识为 {域}.{页面}.{区域}（≥3 段）且区域项声明展示名 / 次序 / 权限码', () => {
    expect(NAMED_SLOT_ID_PATTERN.test(USER_DETAIL_TABS_SLOT)).toBe(true)

    const registration = slotSampleModule.setup({})
    const [extension, detail] = registration.regions ?? []

    expect(extension?.area).toBe(USER_DETAIL_TABS_SLOT)
    expect(extension?.title).toBe('用户扩展示例')
    expect(extension?.order).toBe(20)
    expect(extension?.perm).toBeUndefined()
    expect(typeof extension?.component).toBe('function')

    expect(detail?.order).toBe(30)
    expect(detail?.perm).toBe(USER_EXTENSION_UPDATE_PERMISSION)
    expect(detail?.permMode).toBe('any')
    expect(detail?.area).toBe(USER_DETAIL_TABS_SLOT)
  })

  it('写权限码与后端契约同源（`sys:` 命名空间，归数据归属方）', () => {
    expect(USER_EXTENSION_UPDATE_PERMISSION).toBe('sys:user-extension:update')
  })
})
