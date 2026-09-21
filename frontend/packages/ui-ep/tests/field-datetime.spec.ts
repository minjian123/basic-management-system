// kiwi_id: 969
/** 日期时间字段用例（06_02_01）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { DateTimeField } from '../src'

const ElDatePickerStub = defineComponent({
  name: 'ElDatePicker',
  props: {
    modelValue: { type: [Date, Array], default: undefined },
    type: { type: String, default: 'date' },
    disabled: { type: Boolean, default: false },
    readonly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    format: { type: String, default: undefined },
  },
  emits: ['update:modelValue', 'focus', 'blur'],
  template:
    '<div class="el-date-picker" :data-type="type"><button data-test="pick" @click="$emit(\'update:modelValue\', [new Date(\'2026-09-20\'), new Date(\'2026-09-18\')])" /></div>',
})

const stubs = { ElDatePicker: ElDatePickerStub }

describe('DateTimeField', () => {
  it('形态透传与值回传（Date 对象）', async () => {
    const wrapper = mount(DateTimeField, { props: { modelValue: undefined, kind: 'datetime' }, global: { stubs } })
    expect(wrapper.find('.el-date-picker').attributes('data-type')).toBe('datetime')

    const picked = new Date('2026-09-18T10:00:00+08:00')
    await wrapper.setProps({ modelValue: picked })
    expect(wrapper.findComponent(ElDatePickerStub).props('modelValue')).toEqual(picked)
  })

  it('区间顺序越界发 invalid 且显示内置错误', async () => {
    const wrapper = mount(DateTimeField, {
      props: { modelValue: [new Date('2026-09-20'), new Date('2026-09-18')], kind: 'daterange' },
      global: { stubs },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('invalid')?.[0]).toEqual(['开始时间不能晚于结束时间'])
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('开始时间不能晚于结束时间')
  })

  it('范围校验（min / max）', async () => {
    const wrapper = mount(DateTimeField, {
      props: { modelValue: new Date('2026-09-10'), min: new Date('2026-09-15') },
      global: { stubs },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('不能早于最小时间')

    await wrapper.setProps({ modelValue: new Date('2026-09-30'), min: undefined, max: new Date('2026-09-20') })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('不能晚于最大时间')
  })

  it('必填校验与外部错误优先', async () => {
    const wrapper = mount(DateTimeField, { props: { modelValue: undefined, required: true }, global: { stubs } })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    await wrapper.setProps({ errorMessage: '服务端校验失败' })
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('服务端校验失败')
  })

  it('禁用合并与展示格式透传', () => {
    const wrapper = mount(DateTimeField, {
      props: { modelValue: undefined, disabled: true, displayFormat: 'YYYY/MM/DD' },
      global: { stubs },
    })
    const picker = wrapper.findComponent(ElDatePickerStub)
    expect(picker.props('disabled')).toBe(true)
    expect(picker.props('format')).toBe('YYYY/MM/DD')
  })
})
