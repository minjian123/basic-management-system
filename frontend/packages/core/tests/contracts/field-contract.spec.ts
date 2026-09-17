/**
 * 契约测试（字段编排 · 试点）：组合结构 / 门禁合并 / 校验 / 权限三态。
 */

import { describe, expect, it } from 'vitest'

import { BaseField } from '../../src'

describe('字段编排能力契约（BaseField）', () => {
  it('组合结构：值 / 壳 / 权限三件组合（不重复实现）', () => {
    const field = new BaseField<string>({
      shell: { label: '名称', required: true },
      perm: { editable: true, required: false },
    })
    expect(field.value.key).toBe('value')
    expect(field.shell.label).toBe('名称')
    expect(field.perm.editable).toBe(true)
    expect(field.describe()).toMatchObject({ key: 'field', required: true })
  })

  it('门禁合并：externalDisabled || perm 不可编辑（优先级显式、单一出口）', () => {
    const external = new BaseField<string>({ disabled: true, perm: { editable: true } })
    expect(external.effectiveDisabled).toBe(true)
    external.setValue('x')
    expect(external.getValue()).toBeUndefined() // 拒绝写入

    const byPerm = new BaseField<string>({ perm: { editable: false } })
    expect(byPerm.effectiveDisabled).toBe(true)
    byPerm.setValue('x')
    expect(byPerm.getValue()).toBeUndefined()

    const editable = new BaseField<string>({ perm: { editable: true } })
    editable.setValue('ok')
    expect(editable.getValue()).toBe('ok')
  })

  it('校验触发：必填且空 → 壳错误；有值 → 清除', () => {
    const field = new BaseField<string>({ shell: { required: true } })
    expect(field.validate()).toBe(false)
    expect(field.shell.error.get()).toBe('required')

    field.setValue('v') // setValue 内部触发校验
    expect(field.validate()).toBe(true)
    expect(field.shell.hasError).toBe(false)
  })
})
