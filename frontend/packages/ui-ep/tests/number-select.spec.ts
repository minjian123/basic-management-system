/**
 * 数字框与下拉框（Kiwi 757）——PC / Element Plus 侧。
 *
 * 与 `ui-vant` 侧同名用例同号；跨端不变量见 `contracts-input.spec.ts`，
 * 本文件覆盖 EP 内核细节（`el-input-number` 步进 / 千分位、`el-select` 选项与分组、上限）。
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
  it('NumberInput：内核渲染 / 数值写入 / 越界钳制 / 精度归一', async () => {
    const wrapper = mount(NumberInput, { props: { modelValue: null, min: 0, max: 10 }, global })
    expect(wrapper.find('.bms-number-input').exists()).toBe(true)
    expect(wrapper.find('.el-input-number').exists()).toBe(true)

    await wrapper.find('input').setValue('20')
    await wrapper.find('input').trigger('blur')
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

  it('NumberInput：千分位（只读态格式化）与内核步进控件', () => {
    const wrapper = mount(NumberInput, {
      props: { modelValue: 1234567, thousands: true, step: 1000, readonly: true },
      global,
    })
    expect(wrapper.text(), '只读态千分位').toContain('1,234,567')

    const editable = mount(NumberInput, { props: { modelValue: 1, thousands: true }, global })
    expect(editable.find('.el-input-number__increase').exists(), '内核步进控件').toBe(true)
  })

  it('SelectInput：单选 / 禁用项不可选 / 无效值归一', async () => {
    const wrapper = mount(SelectInput, { props: { modelValue: null, options: OPTIONS }, global })
    expect(wrapper.find('.bms-select-input').exists()).toBe(true)

    const vm = wrapper.vm as unknown as { selectOption: (value: string | number) => void }
    vm.selectOption('b')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('b')

    vm.selectOption('d')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')?.length, '禁用项不写入').toBe(1)

    const ghost = mount(SelectInput, { props: { modelValue: 'ghost', options: OPTIONS, readonly: true }, global })
    expect(ghost.text(), '无效值剔除').not.toContain('ghost')
  })

  it('SelectInput：多选去重保序 / 上限拒绝再选 / 已选可取消', async () => {
    const wrapper = mount(SelectInput, {
      props: { modelValue: ['c', 'a'], options: OPTIONS, multiple: true, readonly: true },
      global,
    })
    expect(wrapper.text().replace(/\s/g, ''), '按选项顺序').toContain('数据A、数据C')

    const limited = mount(SelectInput, {
      props: { modelValue: ['a'], options: OPTIONS, multiple: true, maxCount: 1 },
      global,
    })
    const vm = limited.vm as unknown as { selectOption: (value: string | number) => void }
    vm.selectOption('b')
    await limited.vm.$nextTick()
    expect(limited.emitted('update:modelValue') ?? [], '达上限拒绝').toHaveLength(0)

    vm.selectOption('a')
    await limited.vm.$nextTick()
    expect(limited.emitted('update:modelValue')?.at(-1)?.[0]).toEqual([])
  })
})
