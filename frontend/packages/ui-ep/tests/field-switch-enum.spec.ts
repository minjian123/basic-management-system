/** 开关与枚举字段用例（06_02_03）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { EnumField, InlineSwitchCell, SwitchField, useConfirm } from '../src'

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

const ElSelectStub = defineComponent({
  name: 'ElSelect',
  props: {
    modelValue: { type: [String, Number, Array], default: undefined },
    multiple: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    clearable: { type: Boolean, default: false },
    collapseTags: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'clear'],
  template: '<div class="el-select"><slot /><button data-test="pick-b" @click="$emit(\'update:modelValue\', \'b\')" /><slot name="empty" /></div>',
})

const ElOptionStub = defineComponent({
  name: 'ElOption',
  props: { label: { type: String, default: '' }, value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<div class="el-option">{{ label }}</div>',
})

const ElOptionGroupStub = defineComponent({
  name: 'ElOptionGroup',
  props: { label: { type: String, default: '' } },
  template: '<div class="el-option-group">{{ label }}<slot /></div>',
})

const ElRadioGroupStub = defineComponent({
  name: 'ElRadioGroup',
  props: { modelValue: { type: [String, Number], default: undefined }, disabled: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: '<div class="el-radio-group"><slot /></div>',
})

const ElRadioStub = defineComponent({
  name: 'ElRadio',
  props: { value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<label class="el-radio"><slot /></label>',
})

const ElRadioButtonStub = defineComponent({
  name: 'ElRadioButton',
  props: { value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<label class="el-radio-button"><slot /></label>',
})

const stubs = {
  ElSwitch: ElSwitchStub,
  ElSelect: ElSelectStub,
  ElOption: ElOptionStub,
  ElOptionGroup: ElOptionGroupStub,
  ElRadioGroup: ElRadioGroupStub,
  ElRadio: ElRadioStub,
  ElRadioButton: ElRadioButtonStub,
}

describe('SwitchField', () => {
  it('三态与必填校验', async () => {
    const wrapper = mount(SwitchField, { props: { modelValue: undefined, required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.attributes('data-set')).toBe('false')
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    await wrapper.find('[data-test="switch"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
  })

  it('外部错误覆盖与确认取消不改值', async () => {
    const confirm = useConfirm()
    const wrapper = mount(SwitchField, { props: { modelValue: false, confirm: '确认切换？' }, global: { stubs } })
    const pending = wrapper.find('[data-test="switch"]').trigger('click')
    confirm.resolveConfirm(false)
    await pending
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })
})

describe('InlineSwitchCell', () => {
  it('保存成功写值并派发 saved', async () => {
    const save = vi.fn().mockResolvedValue(undefined)
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(save).toHaveBeenCalledWith(true)
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
    expect(wrapper.emitted('saved')?.[0]).toEqual([true])
  })

  it('保存失败回滚原值并发 invalid', async () => {
    const save = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(InlineSwitchCell, { props: { modelValue: false, save }, global: { stubs } })
    await wrapper.find('[data-test="switch"]').trigger('click')
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.emitted('invalid')?.[0]).toEqual(['保存失败，已回滚'])
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('保存失败，已回滚')
  })
})

describe('EnumField', () => {
  const options = [
    { label: '甲', value: 'a' },
    { label: '乙', value: 'b' },
  ]

  it('下拉默认形态与值回传', async () => {
    const wrapper = mount(EnumField, { props: { modelValue: 'a', options }, global: { stubs } })
    expect(wrapper.findAll('.el-option')).toHaveLength(2)
    await wrapper.find('[data-test="pick-b"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['b'])
  })

  it('单选形态与选项集校验', async () => {
    const radio = mount(EnumField, { props: { modelValue: 'a', options, form: 'button' }, global: { stubs } })
    expect(radio.findAll('.el-radio-button')).toHaveLength(2)

    const invalid = mount(EnumField, { props: { modelValue: 'z' as never, options }, global: { stubs } })
    await invalid.vm.$nextTick()
    expect(invalid.find('[data-test="field-error"]').text()).toBe('选项不在选项集中')
  })

  it('必填与空选项降级', async () => {
    const wrapper = mount(EnumField, { props: { modelValue: undefined, options, required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    const empty = mount(EnumField, { props: { modelValue: undefined, options: [] }, global: { stubs } })
    expect(empty.attributes('data-empty')).toBe('true')
    expect(empty.findComponent(ElSelectStub).props('disabled')).toBe(true)
  })
})
