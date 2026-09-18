/** 级联选择用例（06_02_05）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { CascadeField } from '../src'

const ElCascaderStub = defineComponent({
  name: 'ElCascader',
  props: {
    modelValue: { type: [Array], default: undefined },
    options: { type: Array, default: () => [] },
    props: { type: Object, default: () => ({}) },
    filterable: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-cascader" :data-multiple="props.multiple" :data-strict="props.checkStrictly"><button data-test="pick" @click="$emit(\'update:modelValue\', props.multiple ? [[\'a\', \'a1\'], [\'b\']] : [\'a\', \'a1\'])" /></div>',
})

const stubs = { ElCascader: ElCascaderStub }

const options = [
  {
    value: 'a',
    label: '华东',
    children: [
      { value: 'a1', label: '上海' },
      { value: 'a2', label: '江苏' },
    ],
  },
  { value: 'b', label: '华南' },
]

describe('CascadeField', () => {
  it('单选路径回传与多选路径数组归一', async () => {
    const single = mount(CascadeField, { props: { modelValue: undefined, options }, global: { stubs } })
    await single.find('[data-test="pick"]').trigger('click')
    expect(single.emitted('update:modelValue')?.[0]).toEqual([['a', 'a1']])

    const multi = mount(CascadeField, { props: { modelValue: [['a', 'a1']], options, multiple: true }, global: { stubs } })
    expect(multi.findComponent(ElCascaderStub).props('modelValue')).toEqual([['a', 'a1']])
    expect(multi.findComponent(ElCascaderStub).props('props')).toMatchObject({ multiple: true, checkStrictly: false })
  })

  it('任意级可选与搜索透传', () => {
    const wrapper = mount(CascadeField, {
      props: { modelValue: undefined, options, checkStrictly: true, searchable: true },
      global: { stubs },
    })
    const control = wrapper.findComponent(ElCascaderStub)
    expect(control.props('props')).toMatchObject({ checkStrictly: true })
    expect(control.props('filterable')).toBe(true)
  })

  it('只读路径回显（含未加载路径降级）', () => {
    const wrapper = mount(CascadeField, {
      props: { modelValue: ['a', 'a1'], options, readonly: true },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="cascade-readonly"]').text()).toContain('华东 / 上海')

    const degraded = mount(CascadeField, {
      props: { modelValue: ['x', 'y'], options, readonly: true },
      global: { stubs },
    })
    expect(degraded.find('[data-test="cascade-readonly"]').text()).toContain('x / y')
  })

  it('懒加载失败错误态与重试', async () => {
    const load = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(CascadeField, { props: { modelValue: undefined, lazy: true, load }, global: { stubs } })
    const control = wrapper.findComponent(ElCascaderStub)
    const lazyLoad = (control.props('props') as { lazyLoad: (n: unknown, r: (c: unknown[]) => void, j: () => void) => void }).lazyLoad
    lazyLoad({ value: 'a', label: '华东' }, () => undefined, () => undefined)
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('级联数据加载失败')
    await wrapper.find('[data-test="cascade-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(2)
  })

  it('空态与校验（必填 / 不在级联中）', async () => {
    const empty = mount(CascadeField, { props: { modelValue: undefined, options: [] }, global: { stubs } })
    expect(empty.text()).toContain('暂无数据')

    const required = mount(CascadeField, { props: { modelValue: undefined, options, required: true }, global: { stubs } })
    await required.vm.$nextTick()
    expect(required.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    const missing = mount(CascadeField, { props: { modelValue: ['z'], options }, global: { stubs } })
    await missing.vm.$nextTick()
    expect(missing.find('[data-test="field-error"]').text()).toBe('选项不在级联中')
  })
})
