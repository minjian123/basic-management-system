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

describe('NumberField 精度判定修正（11_03）', () => {
  it('0.29 配 precision=2 不再误报超精度（浮点乘法缺陷修正）', async () => {
    const wrapper = mount(NumberField, { props: { modelValue: 0.29, precision: 2 }, global: { stubs } })
    await wrapper.vm.$nextTick()
    // 旧实现 `Number.isInteger(0.29 * 100)` → 28.999999999999996 → 误报「最多保留 2 位小数」
    expect(wrapper.find('[data-test="field-error"]').exists()).toBe(false)
  })

  it('超精度仍被拦截', async () => {
    const wrapper = mount(NumberField, { props: { modelValue: 1.234, precision: 2 }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('最多保留 2 位小数')
  })

  it('步进对齐校验与单位只读回显（11_03 新增契约）', async () => {
    const aligned = mount(NumberField, { props: { modelValue: 5, step: 5, stepAligned: true }, global: { stubs } })
    await aligned.vm.$nextTick()
    expect(aligned.find('[data-test="field-error"]').exists()).toBe(false)

    const misaligned = mount(NumberField, { props: { modelValue: 3, step: 5, stepAligned: true }, global: { stubs } })
    await misaligned.vm.$nextTick()
    expect(misaligned.find('[data-test="field-error"]').text()).toBe('须为 5 的整数倍')

    const unit = mount(NumberField, { props: { modelValue: 12, unit: '件', readonly: true }, global: { stubs } })
    expect(unit.find('[data-test="number-readonly"]').text()).toBe('12 件')
    const empty = mount(NumberField, { props: { modelValue: undefined, readonly: true }, global: { stubs } })
    expect(empty.find('[data-test="number-readonly"]').text()).toBe('—')
  })
})

describe('AmountField 定点与新增契约（11_03）', () => {
  it('展示走定点字符串分组（不经浮点），带币种与单位', async () => {
    const wrapper = mount(AmountField, { props: { modelValue: '1234567.5', precision: 2, currency: 'CNY', unit: '万元' }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent(ElInputStub).props('modelValue')).toBe('¥1,234,567.50 万元')
  })

  it('中文大写提示（开启时展示，精度不足补零）', async () => {
    const wrapper = mount(AmountField, {
      props: { modelValue: '12345.67', precision: 2, upperCase: true },
      global: { stubs },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="amount-upper"]').text()).toBe('壹万贰仟叁佰肆拾伍元陆角柒分')

    const integral = mount(AmountField, { props: { modelValue: '100', precision: 2, upperCase: true }, global: { stubs } })
    await integral.vm.$nextTick()
    expect(integral.find('[data-test="amount-upper"]').text()).toBe('壹佰元整')

    const off = mount(AmountField, { props: { modelValue: '100', precision: 2 }, global: { stubs } })
    expect(off.find('[data-test="amount-upper"]').exists()).toBe(false)
  })

  it('允许负数开关与只读回显（11_03 新增契约）', async () => {
    const allowed = mount(AmountField, { props: { modelValue: '-5.00', precision: 2, allowNegative: true }, global: { stubs } })
    await allowed.vm.$nextTick()
    expect(allowed.find('[data-test="field-error"]').exists()).toBe(false)

    const blocked = mount(AmountField, { props: { modelValue: '-5.00', precision: 2, allowNegative: false }, global: { stubs } })
    await blocked.vm.$nextTick()
    expect(blocked.find('[data-test="field-error"]').text()).toBe('不允许负数')

    const readonly = mount(AmountField, { props: { modelValue: '1234.5', precision: 2, readonly: true }, global: { stubs } })
    expect(readonly.find('[data-test="amount-readonly"]').text()).toBe('¥1,234.50')
    const empty = mount(AmountField, { props: { modelValue: undefined, readonly: true }, global: { stubs } })
    expect(empty.find('[data-test="amount-readonly"]').text()).toBe('—')
  })
})
