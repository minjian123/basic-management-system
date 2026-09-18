/** 选择类控件用例（05_01_02）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { CheckboxInput, RadioInput, SelectInput, SwitchInput, useConfirm } from '../src'

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
  template: `<div class="el-select">
    <slot />
    <button data-test="select-a" @click="$emit('update:modelValue', multiple ? ['a', 'b'] : 'a')" />
    <button data-test="clear" @click="$emit('clear')" />
    <slot name="empty" />
  </div>`,
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
  template: `<div class="el-radio-group"><slot /><button data-test="radio-b" @click="$emit('update:modelValue', 'b')" /></div>`,
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

const ElSegmentedStub = defineComponent({
  name: 'ElSegmented',
  props: { modelValue: { type: [String, Number], default: undefined }, options: { type: Array, default: () => [] }, disabled: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: `<div class="el-segmented"><button data-test="segmented-b" @click="$emit('update:modelValue', 'b')" /></div>`,
})

const ElCheckboxGroupStub = defineComponent({
  name: 'ElCheckboxGroup',
  props: { modelValue: { type: Array, default: () => [] }, disabled: { type: Boolean, default: false } },
  emits: ['update:modelValue'],
  template: `<div class="el-checkbox-group"><slot /><button data-test="check-ab" @click="$emit('update:modelValue', ['a', 'b'])" /><button data-test="check-a" @click="$emit('update:modelValue', ['a'])" /></div>`,
})

const ElCheckboxStub = defineComponent({
  name: 'ElCheckbox',
  props: {
    modelValue: { type: [Boolean, String, Number], default: false },
    value: { type: [String, Number], default: '' },
    disabled: { type: Boolean, default: false },
    indeterminate: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  template: `<label class="el-checkbox"><slot /><button data-test="checkbox-all" @click="$emit('update:modelValue', true)" /></label>`,
})

const ElCheckboxButtonStub = defineComponent({
  name: 'ElCheckboxButton',
  props: { value: { type: [String, Number], default: '' }, disabled: { type: Boolean, default: false } },
  template: '<label class="el-checkbox-button"><slot /></label>',
})

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
  template: '<button class="el-switch" data-test="switch" @click="$emit(\'update:modelValue\', !modelValue)" />',
})

const stubs = {
  ElSelect: ElSelectStub,
  ElOption: ElOptionStub,
  ElOptionGroup: ElOptionGroupStub,
  ElRadioGroup: ElRadioGroupStub,
  ElRadio: ElRadioStub,
  ElRadioButton: ElRadioButtonStub,
  ElSegmented: ElSegmentedStub,
  ElCheckboxGroup: ElCheckboxGroupStub,
  ElCheckbox: ElCheckboxStub,
  ElCheckboxButton: ElCheckboxButtonStub,
  ElSwitch: ElSwitchStub,
}

const flatOptions = [
  { label: '甲', value: 'a' },
  { label: '乙', value: 'b' },
  { label: '丙', value: 'c', disabled: true },
]

describe('SelectInput', () => {
  it('单选与多选受控值归一', async () => {
    const single = mount(SelectInput, { props: { modelValue: 'x', options: flatOptions }, global: { stubs } })
    await single.find('[data-test="select-a"]').trigger('click')
    expect(single.emitted('update:modelValue')?.[0]).toEqual(['a'])
    expect(single.findAll('.el-option')).toHaveLength(3)

    const multi = mount(SelectInput, { props: { modelValue: [], multiple: true, options: flatOptions }, global: { stubs } })
    await multi.find('[data-test="select-a"]').trigger('click')
    expect(multi.emitted('update:modelValue')?.[0]).toEqual([['a', 'b']])
  })

  it('分组选项与空态插槽', () => {
    const grouped = mount(SelectInput, {
      props: { modelValue: undefined, options: [{ label: '组一', options: flatOptions }] },
      global: { stubs },
    })
    expect(grouped.find('.el-option-group').exists()).toBe(true)
    expect(grouped.findAll('.el-option')).toHaveLength(3)

    const empty = mount(SelectInput, { props: { modelValue: undefined, options: [] }, slots: { empty: '<div data-test="empty">无匹配</div>' }, global: { stubs } })
    expect(empty.find('[data-test="empty"]').exists()).toBe(true)
  })

  it('清空派发 clear 与空值', async () => {
    const wrapper = mount(SelectInput, { props: { modelValue: 'a', clearable: true, options: flatOptions }, global: { stubs } })
    await wrapper.find('[data-test="clear"]').trigger('click')
    expect(wrapper.emitted('clear')).toHaveLength(1)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([undefined])
  })
})

describe('RadioInput', () => {
  it('三形态渲染与值回传', async () => {
    const radio = mount(RadioInput, { props: { modelValue: 'a', options: flatOptions }, global: { stubs } })
    expect(radio.findAll('.el-radio')).toHaveLength(3)
    await radio.find('[data-test="radio-b"]').trigger('click')
    expect(radio.emitted('update:modelValue')?.[0]).toEqual(['b'])

    const button = mount(RadioInput, { props: { modelValue: 'a', options: flatOptions, form: 'button' }, global: { stubs } })
    expect(button.findAll('.el-radio-button')).toHaveLength(3)

    const segmented = mount(RadioInput, { props: { modelValue: 'a', options: flatOptions, form: 'segmented' }, global: { stubs } })
    expect(segmented.findComponent(ElSegmentedStub).exists()).toBe(true)
  })
})

describe('CheckboxInput', () => {
  it('多选回传与全选', async () => {
    const wrapper = mount(CheckboxInput, { props: { modelValue: [], options: flatOptions, selectAll: true }, global: { stubs } })
    await wrapper.find('[data-test="check-ab"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([['a', 'b']])

    await wrapper.find('[data-test="checkbox-all"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([['a', 'b']])
  })

  it('上下限越界派发 invalid 且不改值', async () => {
    const wrapper = mount(CheckboxInput, { props: { modelValue: [], options: flatOptions, max: 1 }, global: { stubs } })
    await wrapper.find('[data-test="check-ab"]').trigger('click')
    expect(wrapper.emitted('invalid')?.[0]).toEqual([['a', 'b']])
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    const lower = mount(CheckboxInput, { props: { modelValue: ['a'], options: flatOptions, min: 2 }, global: { stubs } })
    await lower.find('[data-test="check-a"]').trigger('click')
    expect(lower.emitted('invalid')?.[0]).toEqual([['a']])
  })

  it('tag 形态', () => {
    const wrapper = mount(CheckboxInput, { props: { modelValue: [], options: flatOptions, form: 'tag' }, global: { stubs } })
    expect(wrapper.findAll('.el-checkbox-button')).toHaveLength(3)
  })
})

describe('SwitchInput', () => {
  it('直接切换派发值', async () => {
    const wrapper = mount(SwitchInput, { props: { modelValue: false }, global: { stubs } })
    await wrapper.find('[data-test="switch"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
  })

  it('危险切换确认：取消不改值，确认才改', async () => {
    const confirm = useConfirm()
    const wrapper = mount(SwitchInput, { props: { modelValue: false, confirm: '确认切换？' }, global: { stubs } })

    const pending = wrapper.find('[data-test="switch"]').trigger('click')
    confirm.resolveConfirm(false)
    await pending
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    const again = wrapper.find('[data-test="switch"]').trigger('click')
    confirm.resolveConfirm(true)
    await again
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])
  })
})
