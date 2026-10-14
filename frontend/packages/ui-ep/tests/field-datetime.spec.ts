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
    rangeSeparator: { type: String, default: '-' },
    shortcuts: { type: Array, default: () => [] },
    defaultTime: { type: [Date, Array], default: undefined },
  },
  emits: ['update:modelValue', 'focus', 'blur'],
  template:
    '<div class="el-date-picker" :data-type="type"><button data-test="pick" @click="$emit(\'update:modelValue\', [new Date(\'2026-09-20\'), new Date(\'2026-09-18\')])" /></div>',
})

const ElTimePickerStub = defineComponent({
  name: 'ElTimePicker',
  props: {
    modelValue: { type: [Date, String], default: undefined },
    format: { type: String, default: '' },
    valueFormat: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'focus', 'blur'],
  template: '<div class="el-time-picker" :data-format="format"><button data-test="pick-time" @click="$emit(\'update:modelValue\', \'09:30\')" /></div>',
})

const stubs = { ElDatePicker: ElDatePickerStub, ElTimePicker: ElTimePickerStub }

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

describe('DateTimeField 新增契约（11_03）', () => {
  it('time 形态走时间件（不涉及时区换算）', async () => {
    const wrapper = mount(DateTimeField, { props: { modelValue: undefined, kind: 'time' }, global: { stubs } })
    expect(wrapper.find('.el-time-picker').exists()).toBe(true)
    expect(wrapper.find('.el-date-picker').exists()).toBe(false)
    await wrapper.find('[data-test="pick-time"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['09:30'])
  })

  it('范围分隔符缺省为 ~（EP 缺省为 -）', () => {
    const wrapper = mount(DateTimeField, { props: { modelValue: undefined, kind: 'daterange' }, global: { stubs } })
    expect(wrapper.findComponent(ElDatePickerStub).props('rangeSeparator')).toBe('~')

    const custom = mount(DateTimeField, {
      props: { modelValue: undefined, kind: 'daterange', rangeSeparator: '至' },
      global: { stubs },
    })
    expect(custom.findComponent(ElDatePickerStub).props('rangeSeparator')).toBe('至')
  })

  it('快捷键六项（今天 / 昨天 / 最近 7 天 / 最近 30 天 / 本月 / 上月）', () => {
    const range = mount(DateTimeField, { props: { modelValue: undefined, kind: 'daterange' }, global: { stubs } })
    const shortcuts = range.findComponent(ElDatePickerStub).props('shortcuts') as { text: string }[]
    expect(shortcuts.map((item) => item.text)).toEqual(['今天', '昨天', '最近 7 天', '最近 30 天', '本月', '上月'])

    // 仅区间形态生效
    const single = mount(DateTimeField, { props: { modelValue: undefined, kind: 'date' }, global: { stubs } })
    expect(single.findComponent(ElDatePickerStub).props('shortcuts')).toEqual([])

    const off = mount(DateTimeField, { props: { modelValue: undefined, kind: 'daterange', shortcuts: false }, global: { stubs } })
    expect(off.findComponent(ElDatePickerStub).props('shortcuts')).toEqual([])
  })

  it('默认时分透传', () => {
    const defaultTime = new Date('2026-01-01T00:00:00')
    const wrapper = mount(DateTimeField, { props: { modelValue: undefined, kind: 'datetime', defaultTime }, global: { stubs } })
    expect(wrapper.findComponent(ElDatePickerStub).props('defaultTime')).toEqual(defaultTime)
  })

  it('只读回显：日期 / 日期时间 / 区间「起 ~ 止」/ 时间 / 空值占位', () => {
    const date = mount(DateTimeField, { props: { modelValue: new Date('2026-09-18T10:30:00'), readonly: true }, global: { stubs } })
    expect(date.find('[data-test="datetime-readonly"]').text()).toBe('2026-09-18')

    const datetime = mount(DateTimeField, {
      props: { modelValue: new Date('2026-09-18T10:30:00'), kind: 'datetime', readonly: true },
      global: { stubs },
    })
    expect(datetime.find('[data-test="datetime-readonly"]').text()).toBe('2026-09-18 10:30')

    const range = mount(DateTimeField, {
      props: { modelValue: [new Date('2026-09-01T00:00:00'), new Date('2026-09-11T00:00:00')], kind: 'daterange', readonly: true },
      global: { stubs },
    })
    expect(range.find('[data-test="datetime-readonly"]').text()).toBe('2026-09-01 ~ 2026-09-11')

    const time = mount(DateTimeField, { props: { modelValue: new Date('2026-09-18T09:05:00'), kind: 'time', readonly: true }, global: { stubs } })
    expect(time.find('[data-test="datetime-readonly"]').text()).toBe('09:05')

    const empty = mount(DateTimeField, { props: { modelValue: undefined, readonly: true }, global: { stubs } })
    expect(empty.find('[data-test="datetime-readonly"]').text()).toBe('—')
  })
})
