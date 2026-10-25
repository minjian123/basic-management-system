// kiwi_id: 969
/** 树选择字段用例（06_02_04）。 */

import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { TreeSelectField } from '../src'

const ElTreeSelectStub = defineComponent({
  name: 'ElTreeSelect',
  props: {
    modelValue: { type: [String, Array], default: undefined },
    data: { type: Array, default: () => [] },
    multiple: { type: Boolean, default: false },
    checkStrictly: { type: Boolean, default: false },
    filterable: { type: Boolean, default: false },
    lazy: { type: Boolean, default: false },
    load: { type: Function, default: undefined },
    disabled: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    nodeKey: { type: String, default: 'key' },
    props: { type: Object, default: () => ({}) },
    collapseTags: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'node-click'],
  template: '<div class="el-tree-select" :data-multiple="multiple" :data-strict="checkStrictly" :data-lazy="lazy"><button data-test="pick" @click="$emit(\'update:modelValue\', multiple ? [\'leaf-a\', \'leaf-b\'] : \'leaf-a\')" /></div>',
})

const ElButtonStub = defineComponent({
  name: 'ElButton',
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
})

const stubs = { ElTreeSelect: ElTreeSelectStub, ElButton: ElButtonStub }

const tree = [
  {
    key: 'dept-a',
    label: '研发部',
    children: [
      { key: 'leaf-a', label: '前端组' },
      { key: 'leaf-b', label: '后端组', disabled: true },
    ],
  },
]

describe('TreeSelectField', () => {
  it('单选值回传与策略透传', async () => {
    const wrapper = mount(TreeSelectField, { props: { modelValue: undefined, data: tree }, global: { stubs } })
    const control = wrapper.findComponent(ElTreeSelectStub)
    expect(control.props('multiple')).toBe(false)
    await wrapper.find('[data-test="pick"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['leaf-a'])
  })

  it('多选与独立勾选策略', () => {
    const wrapper = mount(TreeSelectField, {
      props: { modelValue: [], data: tree, multiple: true, checkStrictly: true },
      global: { stubs },
    })
    const control = wrapper.findComponent(ElTreeSelectStub)
    expect(control.props('multiple')).toBe(true)
    expect(control.props('checkStrictly')).toBe(true)
    expect(control.props('modelValue')).toEqual([])
  })

  it('只读路径回显', () => {
    const wrapper = mount(TreeSelectField, {
      props: { modelValue: 'leaf-a', data: tree, readonly: true },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="tree-readonly"]').text()).toContain('研发部 / 前端组')
    expect(wrapper.findComponent(ElTreeSelectStub).exists()).toBe(false)
  })

  it('懒加载失败进入错误态并可重试', async () => {
    const load = vi.fn().mockRejectedValue(new Error('boom'))
    const wrapper = mount(TreeSelectField, {
      props: { modelValue: undefined, lazy: true, load },
      global: { stubs },
    })
    const control = wrapper.findComponent(ElTreeSelectStub)
    const loader = control.props('load') as (node: unknown, resolve: (children: unknown[]) => void, reject: () => void) => void
    loader({ key: 'dept-a', label: '研发部' }, () => undefined, () => undefined)
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()
    expect(load).toHaveBeenCalled()
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('树数据加载失败')
    await wrapper.find('[data-test="tree-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(2)
  })

  it('默认父子独立（11_03 修正缺省语义）', () => {
    const wrapper = mount(TreeSelectField, { props: { modelValue: undefined, data: tree }, global: { stubs } })
    // 节点 §4 明确「父子独立（默认独立，即父节点可单独选中）」
    expect(wrapper.findComponent(ElTreeSelectStub).props('checkStrictly')).toBe(true)
  })

  it('仅叶子可选：非叶子节点标记禁用（11_03 新增契约）', () => {
    const wrapper = mount(TreeSelectField, { props: { modelValue: undefined, data: tree, onlyLeaf: true }, global: { stubs } })
    const effective = wrapper.findComponent(ElTreeSelectStub).props('data') as {
      key: string
      disabled?: boolean
      children?: { key: string; disabled?: boolean }[]
    }[]
    expect(effective[0].disabled).toBe(true)
    expect(effective[0].children?.[0].disabled).toBeFalsy()
  })

  it('排除节点含子树（选上级防环；11_03 新增契约）', () => {
    const wrapper = mount(TreeSelectField, {
      props: { modelValue: undefined, data: tree, excludeSubtree: ['dept-a'] },
      global: { stubs },
    })
    const effective = wrapper.findComponent(ElTreeSelectStub).props('data') as unknown[]
    expect(effective).toHaveLength(0)
  })

  it('多选折叠回显与节点点击（11_03 新增契约）', async () => {
    const wrapper = mount(TreeSelectField, {
      props: { modelValue: ['leaf-a'], data: tree, multiple: true, collapseTags: false },
      global: { stubs },
    })
    expect(wrapper.findComponent(ElTreeSelectStub).props('collapseTags')).toBe(false)

    wrapper.findComponent(ElTreeSelectStub).vm.$emit('node-click', { key: 'leaf-a', label: '前端组' })
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('node-click')?.[0]).toEqual(['leaf-a'])
  })

  it('内容操作暴露：setValue / clear（11_03 新增契约）', async () => {
    const wrapper = mount(TreeSelectField, { props: { modelValue: 'leaf-a', data: tree }, global: { stubs } })
    const exposed = wrapper.vm as unknown as { clear: () => void }
    exposed.clear()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([undefined])
  })

  it('空态与校验（必填 / 不在树中）', async () => {
    const empty = mount(TreeSelectField, { props: { modelValue: undefined, data: [] }, global: { stubs } })
    expect(empty.text()).toContain('暂无数据')

    const required = mount(TreeSelectField, { props: { modelValue: undefined, data: tree, required: true }, global: { stubs } })
    await required.vm.$nextTick()
    expect(required.find('[data-test="field-error"]').text()).toBe('该字段为必填项')

    const missing = mount(TreeSelectField, { props: { modelValue: 'ghost', data: tree }, global: { stubs } })
    await missing.vm.$nextTick()
    expect(missing.find('[data-test="field-error"]').text()).toBe('选项不在树中')
  })
})
