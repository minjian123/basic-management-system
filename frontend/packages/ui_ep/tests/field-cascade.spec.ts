// kiwi_id: 969
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
    showAllLevels: { type: Boolean, default: true },
    clearable: { type: Boolean, default: true },
  },
  emits: ['update:modelValue'],
  template: '<div class="el-cascader" :data-multiple="props.multiple" :data-strict="props.checkStrictly"><button data-test="pick" @click="$emit(\'update:modelValue\', props.multiple ? [[\'a\', \'a1\'], [\'b\']] : [\'a\', \'a1\'])" /></div>',
})

const ElButtonStub = defineComponent({
  name: 'ElButton',
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
})

const stubs = { ElCascader: ElCascaderStub, ElButton: ElButtonStub }

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

  it('路径展示 / 展开触发 / 可清除 / emitPath 显式化（11_03 新增契约）', () => {
    const defaults = mount(CascadeField, { props: { modelValue: undefined, options }, global: { stubs } })
    const control = defaults.findComponent(ElCascaderStub)
    // emitPath 显式化为 true，不依赖 element-plus 版本默认值
    expect(control.props('props')).toMatchObject({ emitPath: true, expandTrigger: 'click' })
    expect(control.props('showAllLevels')).toBe(true)
    expect(control.props('clearable')).toBe(true)

    const custom = mount(CascadeField, {
      props: { modelValue: undefined, options, pathDisplay: false, expandTrigger: 'hover', clearable: false, emitPath: false },
      global: { stubs },
    })
    const customControl = custom.findComponent(ElCascaderStub)
    expect(customControl.props('props')).toMatchObject({ emitPath: false, expandTrigger: 'hover' })
    expect(customControl.props('showAllLevels')).toBe(false)
    expect(customControl.props('clearable')).toBe(false)
  })

  it('内容操作暴露：setValue / clear / selectedNodes（11_03 新增契约）', async () => {
    const wrapper = mount(CascadeField, { props: { modelValue: ['a', 'a1'], options }, global: { stubs } })
    const exposed = wrapper.vm as unknown as {
      selectedNodes: () => string[][]
      clear: () => void
    }
    expect(exposed.selectedNodes()).toEqual([['a', 'a1']])
    exposed.clear()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([undefined])
  })

  it('懒加载中标记 loading（11_03 新增契约）', async () => {
    let release: (children: Record<string, unknown>[]) => void = () => {}
    const load = vi.fn().mockImplementation(
      () =>
        new Promise<Record<string, unknown>[]>((resolve) => {
          release = resolve
        }),
    )
    const wrapper = mount(CascadeField, { props: { modelValue: undefined, lazy: true, load }, global: { stubs } })
    const control = wrapper.findComponent(ElCascaderStub)
    const lazyLoad = (control.props('props') as { lazyLoad: (n: unknown, r: (c: Record<string, unknown>[]) => void, j: () => void) => void }).lazyLoad
    lazyLoad({ value: 'a', label: '华东' }, () => undefined, () => undefined)
    await wrapper.vm.$nextTick()
    expect(wrapper.attributes('data-loading')).toBe('true')
    release([])
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()
    expect(wrapper.attributes('data-loading')).toBe('false')
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
    expect(load).toHaveBeenCalledTimes(1)
    await wrapper.find('[data-test="cascade-retry"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.emitted('retry')).toHaveLength(2)
    // 重试**先重放请求**（与 TransferField 口径统一）
    expect(load).toHaveBeenCalledTimes(2)
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
