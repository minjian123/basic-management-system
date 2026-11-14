/**
 * 字典树字段用例：与字典选择同一数据通路（`dataSourceKey` + `DictSourceAdapter`），
 * 覆盖整树组树、超阈值懒加载、未注入占位、错误态、只读路径回显、字典标识切换。
 */

import type { DictItem, DictSourceAdapter, DictSourceTypeQuery } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DictTreeField, TreeSelectField } from '../src'

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
  emits: ['update:modelValue'],
  template: '<div class="el-tree-select" :data-lazy="lazy" />',
})

const stubs = { ElTreeSelect: ElTreeSelectStub }

/**
 * 构造字典条目。
 *
 * @param id 条目 id。
 * @param parentId 父 id。
 * @param label 文案。
 * @param sort 排序值。
 */
function item(id: string, parentId: string | undefined, label: string, sort = 0): DictItem {
  return { id, parentId, label, code: id, value: id, sort, status: 'enabled' }
}

const treeItems = [
  item('root', '0', '总部', 1),
  item('a', 'root', '研发部', 2),
  item('a1', 'a', '前端组', 1),
  item('a2', 'a', '后端组', 2),
]

describe('DictTreeField', () => {
  // 字典缓存落 localStorage（跨测试共享）：每例清空，避免上一例的大字典 / 版本状态污染本例请求次数
  beforeEach(() => {
    localStorage.clear()
  })

  it('未注入数据源即占位零请求', async () => {
    const wrapper = mount(DictTreeField, {
      props: { dataSourceKey: 'mdm_dept' },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="placeholder"]').exists()).toBe(true)
    expect(wrapper.findComponent(TreeSelectField).exists()).toBe(false)
  })

  it('整树模式：一次取全量并按 parentId 组树', async () => {
    const getType = vi.fn(async () => ({ version: 1, items: treeItems, hasMore: false, total: treeItems.length }))
    const wrapper = mount(DictTreeField, {
      props: { dataSourceKey: 'mdm_dept', source: { getType } as unknown as DictSourceAdapter },
      global: { stubs },
    })
    await flushPromises()
    const tree = wrapper.findComponent(TreeSelectField)
    expect(tree.exists()).toBe(true)
    expect(tree.props('lazy')).toBe(false)
    const data = tree.props('data') as Array<{ key: string; children?: Array<{ key: string }> }>
    expect(data.map((node) => node.key)).toEqual(['root'])
    expect(data[0]?.children?.map((node) => node.key)).toEqual(['a'])
    expect(getType).toHaveBeenCalledTimes(1)
  })

  it('超阈值转懒加载：根节点按顶层拉取', async () => {
    const getType = vi.fn(async (query: DictSourceTypeQuery) => {
      if (query.parentId === '0') {
        return { version: 1, items: [item('root', '0', '总部')], hasMore: false, total: 1 }
      }
      return { version: 1, items: treeItems, hasMore: true, total: 5000 }
    })
    const wrapper = mount(DictTreeField, {
      props: { dataSourceKey: 'mdm_dept', source: { getType } as unknown as DictSourceAdapter },
      global: { stubs },
    })
    await flushPromises()
    const tree = wrapper.findComponent(TreeSelectField)
    expect(tree.props('lazy')).toBe(true)
    expect((tree.props('data') as Array<{ key: string }>).map((node) => node.key)).toEqual(['root'])
    expect(getType).toHaveBeenCalledTimes(2)
    expect(getType.mock.calls[1]?.[0]).toMatchObject({ parentId: '0' })
  })

  it('懒加载子节点按 parentId 取数', async () => {
    const getType = vi.fn(async (query: DictSourceTypeQuery) => {
      if (query.parentId === '0') {
        return { version: 1, items: [item('root', '0', '总部')], hasMore: false, total: 1 }
      }
      if (query.parentId === 'root') {
        return { version: 1, items: [item('a', 'root', '研发部')], hasMore: false, total: 1 }
      }
      return { version: 1, items: treeItems, hasMore: true, total: 5000 }
    })
    const wrapper = mount(DictTreeField, {
      props: { dataSourceKey: 'mdm_dept', source: { getType } as unknown as DictSourceAdapter },
      global: { stubs },
    })
    await flushPromises()
    const tree = wrapper.findComponent(TreeSelectField)
    const load = tree.props('load') as unknown as (node: { key: string }) => Promise<Array<{ key: string }>>
    const children = await load({ key: 'root' })
    expect(children.map((node) => node.key)).toEqual(['a'])
  })

  it('取数失败进入错误态', async () => {
    const getType = vi.fn(async () => {
      throw new Error('字典不可用')
    })
    const wrapper = mount(DictTreeField, {
      props: { dataSourceKey: 'mdm_dept', source: { getType } as unknown as DictSourceAdapter },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="error"]').text()).toContain('字典不可用')
  })

  it('只读回显按树路径展示', async () => {
    const getType = vi.fn(async () => ({ version: 1, items: treeItems, hasMore: false, total: treeItems.length }))
    const wrapper = mount(DictTreeField, {
      props: {
        dataSourceKey: 'mdm_dept',
        source: { getType } as unknown as DictSourceAdapter,
        modelValue: 'a1',
        readonly: true,
      },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="dict-tree-readonly"]').text()).toContain('总部 / 研发部 / 前端组')
  })

  it('字典标识切换触发重新取数', async () => {
    const getType = vi.fn(async (query: DictSourceTypeQuery) => {
      void query
      return { version: 1, items: treeItems, hasMore: false, total: treeItems.length }
    })
    const wrapper = mount(DictTreeField, {
      props: { dataSourceKey: 'mdm_dept', source: { getType } as unknown as DictSourceAdapter },
      global: { stubs },
    })
    await flushPromises()
    expect(getType).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ dataSourceKey: 'mdm_post' })
    await flushPromises()
    expect(getType).toHaveBeenCalledTimes(2)
    expect(getType.mock.calls[1]?.[0]).toMatchObject({ dataSourceKey: 'mdm_post' })
  })
})
