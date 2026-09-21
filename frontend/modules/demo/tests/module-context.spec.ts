// kiwi_id: 980
/** 演示模块注入上下文消费用例（只读快照 + 缺失降级；需求 05-5 运行时约束口径）。 */

import type { ModuleRegistration } from '@bms/core'
import { describe, expect, it } from 'vitest'

import demoModule from '../src/index'

/**
 * 取中文文案包的问候文案。
 *
 * @param registration 模块注册声明。
 * @returns 问候文案（缺省空串）。
 */
function zhHello(registration: ModuleRegistration): string {
  const pack = registration.i18nPacks?.find((item) => item.key === 'demo:zh-cn')
  return pack?.messages['demo.hello'] ?? ''
}

describe('演示模块注入上下文消费（Kiwi 980）', () => {
  it('经 setup(context) 只读消费宿主能力：上下文缺失时自行降级', () => {
    expect(zhHello(demoModule.setup({}))).toBe('你好，演示模块')
  })

  it('上下文存在时按只读快照消费（不直连宿主 store / router）', () => {
    const registration = demoModule.setup({ user: ['sys:user:list', 'sys:user:add'] })
    expect(zhHello(registration)).toBe('你好，已接入 2 项权限')
  })
})
