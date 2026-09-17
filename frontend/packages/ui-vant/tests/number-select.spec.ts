/**
 * 数字框与下拉框（Kiwi 757）——移动端 / Vant 侧。
 *
 * 与 `ui-ep` 侧同名用例同号；跨端不变量见 `contracts-input.spec.ts`，
 * 本文件覆盖 Vant 内核细节（数字键盘 / 可选步进按钮 / 底部面板分组与多选确认）。
 */

import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'

import { NumberInput, SelectInput } from '../src'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      common: { confirm: '确定' },
      input: {
        required: '必填项',
        emptyText: '—',
        outOfRange: '数值超出允许范围',
        selectPlaceholder: '请选择',
        searchPlaceholder: '搜索',
        maxCount: '最多可选 {max} 项',
        password: { weak: '弱', medium: '中', strong: '强', show: '显示', hide: '隐藏' },
      },
    },
  },
})
const global = { plugins: [i18n] }

const OPTIONS = [
  { value: 'a', label: '数据 A' },
  { value: 'b', label: '数据 B', group: '组一' },
  { value: 'c', label: '数据 C', group: '组一' },
  { value: 'd', label: '数据 D', disabled: true },
]

describe('数字框与下拉框（Kiwi 757）', () => {
  it('NumberInput：数字键盘内核 / 输入解析 / 失焦钳制与精度', async () => {
    const wrapper = mount(NumberInput, { props: { modelValue: null, min: 0, max: 10 }, global })
    expect(wrapper.find('.bms-number-input').exists()).toBe(true)
    const input = wrapper.find('input')
    expect(input.exists()).toBe(true)

    await input.setValue('20')
    await input.trigger('blur')
    expect(wrapper.emitted('change')?.at(-1)?.[0]).toBe(10)

    const loose = mount(NumberInput, { props: { modelValue: null, clamp: false, min: 0, max: 10 }, global })
    await loose.find('input').setValue('20')
    await loose.find('input').trigger('blur')
    expect(loose.emitted('validate')?.at(-1)?.[0]).toBe(false)
    expect(loose.text()).toContain('数值超出允许范围')

    const precise = mount(NumberInput, { props: { modelValue: null, precision: 1 }, global })
    await precise.find('input').setValue('1.2')
    await precise.find('input').trigger('blur')
    expect(precise.emitted('change')?.at(-1)?.[0]).toBe(1.2)

    const rounded = mount(NumberInput, { props: { modelValue: null }, global })
    await rounded.find('input').setValue('1.6')
    await rounded.find('input').trigger('blur')
    expect(rounded.emitted('change')?.at(-1)?.[0]).toBe(2)
  })

  it('NumberInput：千分位显示与可选步进按钮（`step` 生效）', async () => {
    const wrapper = mount(NumberInput, {
      props: { modelValue: 1234567, thousands: true, readonly: true },
      global,
    })
    expect(wrapper.text(), '只读态千分位').toContain('1,234,567')

    const stepper = mount(NumberInput, { props: { modelValue: 5, stepControls: true, step: 2 }, global })
    const buttons = stepper.findAll('.bms-number-input-step')
    expect(buttons.length, '加减按钮').toBe(2)
    await buttons[1]?.trigger('click')
    expect(stepper.emitted('update:modelValue')?.at(-1)?.[0]).toBe(7)
    await buttons[0]?.trigger('click')
    expect(stepper.emitted('update:modelValue')?.at(-1)?.[0]).toBe(5)
  })

  it('SelectInput：触发区渲染已选文本 / 面板分组与选项 / 多选确认按钮', async () => {
    const wrapper = mount(SelectInput, {
      props: { modelValue: ['b'], options: OPTIONS, multiple: true, maxCount: 2, filterable: true },
      global,
      attachTo: document.body,
    })
    expect(wrapper.find('.bms-select-input-trigger').text()).toContain('数据 B')

    await wrapper.find('.bms-select-input-trigger').trigger('click')
    await wrapper.vm.$nextTick()

    expect(document.body.querySelector('.bms-select-input-panel'), '面板打开').not.toBeNull()
    expect(document.body.querySelectorAll('.bms-select-input-option').length, '选项数量').toBe(
      OPTIONS.length,
    )
    expect(document.body.querySelector('.bms-select-input-group')?.textContent).toContain('组一')
    expect(document.body.querySelector('.bms-select-input-actions button'), '多选确认按钮').not.toBeNull()

    wrapper.unmount()
  })

  it('SelectInput：单选即写域 / 禁用项不可选 / 上限拒绝再选', async () => {
    const single = mount(SelectInput, { props: { modelValue: null, options: OPTIONS }, global })
    const singleVm = single.vm as unknown as { selectOption: (value: string | number) => void }
    singleVm.selectOption('c')
    await single.vm.$nextTick()
    expect(single.emitted('update:modelValue')?.at(-1)?.[0]).toBe('c')

    singleVm.selectOption('d')
    await single.vm.$nextTick()
    expect(single.emitted('update:modelValue')?.length, '禁用项不写入').toBe(1)

    const limited = mount(SelectInput, {
      props: { modelValue: ['a'], options: OPTIONS, multiple: true, maxCount: 1 },
      global,
    })
    const limitedVm = limited.vm as unknown as { selectOption: (value: string | number) => void }
    limitedVm.selectOption('b')
    await limited.vm.$nextTick()
    expect(limited.emitted('update:modelValue') ?? [], '达上限拒绝').toHaveLength(0)
  })
})
