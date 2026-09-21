// kiwi_id: 969
/** 数值与金额字段用例（06_02_02）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { AmountField, NumberField } from '../src'

const ElInputNumberStub = defineComponent({
  name: 'ElInputNumber',
  props: {
    modelValue: { type: Number, default: undefined },
    min: { type: Number, default: undefined },
    max: { type: Number, default: undefined },
    step: { type: Number, default: 1 },
    precision: { type: Number, default: undefined },
    disabled: { type: Boolean, default: false },
    readonly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-input-number" :data-precision="precision"><button data-test="set" @click="$emit(\'update:modelValue\', 1.239)" /></div>',
})

const ElInputStub = defineComponent({
  name: 'ElInput',
  props: {
    modelValue: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
    readonly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'focus', 'blur'],
  template: '<div class="el-input"><input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @focus="$emit(\'focus\')" @blur="$emit(\'blur\')" /></div>',
})

const stubs = { ElInputNumber: ElInputNumberStub, ElInput: ElInputStub }

describe('NumberField', () => {
  it('精度归一与范围校验', async () => {
    const wrapper = mount(NumberField, { props: { modelValue: undefined, precision: 2, max: 1 }, global: { stubs } })
    await wrapper.find('[data-test="set"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([1.24])
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('不能大于 1')

    const min = mount(NumberField, { props: { modelValue: 0.5, min: 1 }, global: { stubs } })
    await min.vm.$nextTick()
    expect(min.find('[data-test="field-error"]').text()).toBe('不能小于 1')
  })

  it('必填与外部错误优先', async () => {
    const wrapper = mount(NumberField, { props: { modelValue: undefined, required: true, precision: 0 }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })
})

describe('AmountField', () => {
  it('十进制字符串保真与厘 / 毫精度归一', async () => {
    const wrapper = mount(AmountField, { props: { modelValue: '', precision: 4 }, global: { stubs } })
    await wrapper.find('input').setValue('1.23456')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['1.2346'])

    const cents = mount(AmountField, { props: { modelValue: '', precision: 3 }, global: { stubs } })
    await cents.find('input').setValue('1.2345')
    expect(cents.emitted('update:modelValue')?.[0]).toEqual(['1.235'])
  })

  it('范围校验与外部覆盖', async () => {
    const wrapper = mount(AmountField, { props: { modelValue: '200.00', precision: 2, max: '100' }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('不能大于 100')

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })

  it('非法输入不写值并告警；必填校验', async () => {
    const wrapper = mount(AmountField, { props: { modelValue: '', required: true }, global: { stubs } })
    await wrapper.find('input').setValue('abc')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')
  })

  it('千分位展示（失焦态）与精度透传', () => {
    const wrapper = mount(AmountField, { props: { modelValue: '1234567.5', precision: 2 }, global: { stubs } })
    expect(wrapper.find('input').attributes('value')).toContain('1,234,567.5')
  })
})
