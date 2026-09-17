/** 主树用例（Kiwi 734）：搜索 / 选中 / 多选 / 计数 / 维护入口。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import MasterTree from '@/components/layout/MasterTree.vue'
import type { TreeNode } from '@/components/layout/useMasterDetail'

import { mountWithPlugins } from './helpers/mount'

const hasPermMock = vi.hoisted(() => vi.fn<(codes: string[]) => boolean>(() => true))

vi.mock('@/utils/perm', () => ({ hasPerm: (codes: string[]) => hasPermMock(codes) }))

beforeEach(() => {
  hasPermMock.mockReset().mockReturnValue(true)
})

afterEach(() => {
  vi.useRealTimers()
})

const TREE: TreeNode[] = [
  {
    id: '1',
    label: '总部',
    count: 12,
    children: [
      { id: '1-1', label: '研发部', count: 5 },
      { id: '1-2', label: '市场部', count: 7 },
    ],
  },
]

function mountTree(props: Record<string, unknown> = {}) {
  return mountWithPlugins(MasterTree, {
    props: { treeData: TREE, ...props },
  })
}

function visibleNodeTexts(wrapper: ReturnType<typeof mountTree>): string[] {
  return wrapper
    .findAll('.el-tree-node')
    .filter((node) => !(node.attributes('style') ?? '').includes('display: none'))
    .map((node) => node.find('.el-tree-node__content').text())
}

describe('主树（Kiwi 734）', () => {
  it('渲染树节点与 defaultExpandAll', async () => {
    const collapsed = mountTree()
    await nextTick()
    expect(visibleNodeTexts(collapsed).join(' ')).toContain('总部')

    const expanded = mountTree({ defaultExpandAll: true })
    await nextTick()
    const texts = visibleNodeTexts(expanded).join(' ')
    expect(texts).toContain('总部')
    expect(texts).toContain('研发部')
    expect(texts).toContain('市场部')
  })

  it('搜索过滤：防抖后命中可见、未命中隐藏', async () => {
    const wrapper = mountTree({ defaultExpandAll: true })
    await nextTick()

    vi.useFakeTimers()
    await wrapper.find('input').setValue('研发')
    vi.advanceTimersByTime(500)
    await nextTick()
    await nextTick()

    const texts = visibleNodeTexts(wrapper).join(' ')
    expect(texts).toContain('研发部')
    expect(texts).not.toContain('市场部')
  })

  it('点击节点 emit select；checkable 渲染复选框并 emit check', async () => {
    const wrapper = mountTree({ defaultExpandAll: true })
    await nextTick()
    const content = wrapper.findAll('.el-tree-node__content').at(1)
    await content?.trigger('click')
    expect(wrapper.emitted('select')?.at(-1)?.[0]).toMatchObject({ id: '1-1', label: '研发部' })

    const checked = mountTree({ defaultExpandAll: true, checkable: true })
    await nextTick()
    expect(checked.find('.el-checkbox').exists()).toBe(true)
    checked.findComponent({ name: 'ElTree' }).vm.$emit('check')
    await nextTick()
    expect(checked.emitted('check')).toBeTruthy()

    expect(mountTree().find('.el-checkbox').exists()).toBe(false)
  })

  it('showCount 渲染计数', async () => {
    const wrapper = mountTree({ showCount: true })
    await nextTick()
    expect(wrapper.find('.bms-master-tree-node-count').text()).toBe('12')
  })

  it('维护入口：工具栏与权限过滤', async () => {
    const wrapper = mountTree({ managePermission: ['org:manage'] })
    await nextTick()

    const buttons = wrapper.findAll('button').map((button) => button.text())
    expect(buttons).toEqual(['新增', '编辑', '删除', '刷新'])

    // 编辑 / 删除未选中时禁用
    expect(
      wrapper.findAll('button').filter((button) => button.text() === '编辑')?.[0]?.attributes('disabled'),
    ).toBeDefined()

    await wrapper.findAll('button').find((button) => button.text() === '新增')?.trigger('click')
    expect(wrapper.emitted('node-create')?.at(-1)).toEqual([null])

    await wrapper.findAll('button').find((button) => button.text() === '刷新')?.trigger('click')
    expect(wrapper.emitted('refresh')?.at(-1)).toEqual([null])

    hasPermMock.mockReturnValue(false)
    const denied = mountTree({ managePermission: ['org:manage'] })
    await nextTick()
    expect(denied.findAll('button').map((button) => button.text())).toEqual([])
  })

  it('选中后编辑 / 删除 emit 与右键菜单', async () => {
    const wrapper = mountTree()
    await nextTick()
    await wrapper.findAll('.el-tree-node__content').at(0)?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '编辑')?.trigger('click')
    expect(wrapper.emitted('node-edit')?.at(-1)?.[0]).toMatchObject({ id: '1' })

    wrapper
      .findComponent({ name: 'ElTree' })
      .vm.$emit('node-contextmenu', new MouseEvent('contextmenu', { clientX: 10, clientY: 10 }), TREE[0]?.children?.[0])
    await nextTick()
    expect(wrapper.findAll('.bms-master-tree-menu-item').length).toBe(4)
    await wrapper
      .findAll('.bms-master-tree-menu-item')
      .find((item) => item.text() === '删除')
      ?.trigger('click')
    expect(wrapper.emitted('node-delete')?.at(-1)?.[0]).toMatchObject({ id: '1-1' })
  })

  it('空树 EmptyState（含新增入口）与 loading 骨架', async () => {
    const empty = mountTree({ treeData: [] })
    await nextTick()
    expect(empty.text()).toContain('暂无数据')
    await empty.findAll('button').find((button) => button.text() === '新增')?.trigger('click')
    expect(empty.emitted('node-create')).toBeTruthy()

    const loading = mountTree({ loading: true })
    expect(loading.find('.bms-skeleton').exists()).toBe(true)
  })
})
