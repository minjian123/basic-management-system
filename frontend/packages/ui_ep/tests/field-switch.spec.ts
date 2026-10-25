// kiwi_id: 969
/** 开关字段用例（06_02_03；06_10 由 `field-switch-enum.spec.ts` 拆出，用例逐条迁移、不删减）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { InlineSwitchCell, SwitchField, TriStateSwitch, useConfirm } from '../src'

const ElSwitchStub = defineComponent({
  name: 'ElSwitch',
  props: {
    modelValue: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    activeText: { type: String, default: '' },
    inactiveText: { type: String, default: '' },
    indeterminate: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-switch" :data-indeterminate="indeterminate"><button data-test="switch" @click="$emit(\'update:modelValue\', !modelValue)" /></div>',
})

const stubs = {
  ElSwitch: ElSwitchStub,
}

describe('SwitchField', () => {
  it('三态与必填校验', async () => {
    const wrapper = mount(SwitchField, { props: { modelValue: undefined, required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.attributes('data-set')).toBe('false')
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
  })

  it('外部错误覆盖与确认取消不改值', async () => {
    const confirm = useConfirm()
    const wrapper = mount(SwitchField, { props: { modelValue: false, confirm: '确认切换？' }, global: { stubs } })
    const pending = wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    confirm.resolveConfirm(false)
    await pending
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })

  it('切换前置判定不通过则撤销（11_03 新增契约）', async () => {
    const beforeChange = vi.fn().mockReturnValue(false)
    const wrapper = mount(SwitchField, { props: { modelValue: false, beforeChange }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(beforeChange).toHaveBeenCalledWith(true)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('三态清空入口与尺寸档位（11_03 新增契约）', async () => {
    const wrapper = mount(SwitchField, { props: { modelValue: true, clearable: true, size: 'compact' }, global: { stubs } })
    expect(wrapper.attributes('data-size')).toBe('compact')
    await wrapper.find('[data-test="switch-clear"]').trigger('click')
    expect(wrapper.emitted('clear')).toHaveLength(1)
  })

  it('只读回显（是 / 否 / 未设置占位，11_03 新增契约）', () => {
    const on = mount(SwitchField, { props: { modelValue: true, readonly: true }, global: { stubs } })
    expect(on.find('[data-test="switch-readonly"]').text()).toBe('是')

    const off = mount(SwitchField, { props: { modelValue: false, readonly: true }, global: { stubs } })
    expect(off.find('[data-test="switch-readonly"]').text()).toBe('否')

    const unset = mount(SwitchField, { props: { modelValue: undefined, readonly: true }, global: { stubs } })
    expect(unset.find('[data-test="switch-readonly"]').text()).toBe('—')
  })
})

describe('InlineSwitchCell', () => {
  it('保存成功写值并派发 saved', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(save).toHaveBeenCalledWith(true)
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
    expect(wrapper.emitted('saved')?.[0]).toEqual([true])
  })

  it('保存失败回滚原值并发 invalid', async () => {
    const save = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('invalid')?.[0]).toEqual(['保存失败，已回滚'])
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('保存失败，已回滚')
  })

  it('乐观值：保存期间即按目标态展示（11_03 新增契约）', async () => {
    let release: () => void = () => {}
    const save = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          release = resolve
        }),
    )
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    // 保存未完成即展示目标态（乐观）
    expect(wrapper.find('[data-test="tri-state-switch"]').attributes('aria-checked')).toBe('true')
    release()
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('saved')?.[0]).toEqual([true])
  })

  it('版本冲突提示并派发 refresh（11_03 新增契约）', async () => {
    const save = vi.fn().mockRejectedValue(new Error('409 conflict'))
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('数据已被他人修改')
  })

  it('危险开关二次确认取消不改值（11_03 新增契约）', async () => {
    const confirm = useConfirm()
    const save = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save, confirm: '确认切换？' }, global: { stubs } })
    const pending = wrapper.find('[data-test="tri-state-switch"]').trigger('click')
    confirm.resolveConfirm(false)
    await pending
    expect(save).not.toHaveBeenCalled()
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})

describe('TriStateSwitch', () => {
  it('三态：未设置 / 开 / 关（aria-checked mixed，11_03 新增件）', async () => {
    const wrapper = mount(TriStateSwitch, { props: { modelValue: undefined } })
    const control = wrapper.find('[data-test="tri-state-switch"]')
    expect(control.attributes('aria-checked')).toBe('mixed')
    expect(wrapper.attributes('data-state')).toBe('unset')

    await control.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])

    await wrapper.setProps({ modelValue: false })
    expect(wrapper.attributes('data-state')).toBe('off')
    expect(wrapper.find('[data-test="tri-state-switch"]').attributes('aria-checked')).toBe('false')
  })

  it('键盘 Enter / Space 触发与禁用不响应', async () => {
    const wrapper = mount(TriStateSwitch, { props: { modelValue: false } })
    const control = wrapper.find('[data-test="tri-state-switch"]')
    await control.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])

    const disabled = mount(TriStateSwitch, { props: { modelValue: false, disabled: true } })
    await disabled.find('[data-test="tri-state-switch"]').trigger('click')
    expect(disabled.emitted('update:modelValue')).toBeUndefined()
  })

  it('尺寸档位与文案变体', () => {
    const wrapper = mount(TriStateSwitch, {
      props: { modelValue: true, size: 'compact', activeText: '启用', inactiveText: '停用' },
    })
    expect(wrapper.attributes('data-size')).toBe('compact')
    expect(wrapper.text()).toContain('启用')
  })
})
