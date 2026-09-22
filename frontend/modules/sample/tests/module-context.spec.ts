// kiwi_id: 983
/** 样例模块注入上下文消费用例（只读快照 + 缺失降级；需求 05-5 运行时约束口径）。 */

import { describe, expect, it } from 'vitest'

import sampleModule from '../src/index'
import { SAMPLE_EDIT_PERMISSION, sampleRuntime } from '../src/runtime'

describe('样例模块注入上下文消费（Kiwi 982）', () => {
  it('空上下文自行降级：无权限信息时按可编辑（样例演示口径）', () => {
    sampleModule.setup({})
    expect(sampleRuntime()).toEqual({ permissionCount: 0, canEdit: true })
  })

  it('按只读快照消费权限码：无编辑权限时降级只读', () => {
    sampleModule.setup({ user: ['sample:record:view'] })
    expect(sampleRuntime()).toEqual({ permissionCount: 1, canEdit: false })
  })

  it('命中编辑权限码时可编辑', () => {
    sampleModule.setup({ user: ['sample:record:view', SAMPLE_EDIT_PERMISSION] })
    expect(sampleRuntime()).toEqual({ permissionCount: 2, canEdit: true })
  })
})
