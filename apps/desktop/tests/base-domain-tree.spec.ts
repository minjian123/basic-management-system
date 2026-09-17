/** 树域基类用例（Kiwi 711）：归一 / 懒加载 / 选择勾选 / 过滤保留祖先（双端同款）。 */

import { describe, expect, it } from 'vitest'
import { h } from 'vue'

import { BaseTree, useTreeBase, type TreeNode } from '@/components/base'

import { mountWithPlugins } from './helpers/mount'

const data: TreeNode[] = [
  {
    key: 'a',
    label: 'A',
    children: [
      { key: 'a1', label: 'A1' },
      { key: 'a2', label: 'A2', children: [{ key: 'a2x', label: 'AX' }] },
    ],
  },
  { key: 'b', label: 'B' },
]

function firstNode(tree: TreeNode[]): TreeNode {
  const node = tree[0]
  if (!node) {
    throw new Error('树数据为空')
  }
  return node
}

describe('树域基类（Kiwi 711）', () => {
  it('① 静态数据归一与占位（不请求）', async () => {
    const tree = useTreeBase({ data })
    expect(tree.isPlaceholder).toBe(true)
    expect(tree.treeData.map((node) => node.key)).toEqual(['a', 'b'])
    expect(tree.treeData[0]?.children?.map((node) => node.key)).toEqual(['a1', 'a2'])
    const roots = await tree.loadRoot()
    expect(roots).toHaveLength(2)
  })

  it('② 懒加载：loading / loaded / 根与子级加载', async () => {
    const loaded: string[] = []
    let resolveRoot: ((rows: unknown[]) => void) | undefined
    const rootPromise = new Promise<unknown[]>((resolve) => {
      resolveRoot = resolve
    })
    const tree = useTreeBase({
      nodeKey: 'id',
      onLoaded: (node) => loaded.push(node.key),
      load: (node) => {
        if (node) {
          return Promise.resolve([{ id: `${node.key}-child`, label: 'child' }])
        }
        return rootPromise
      },
    })
    expect(tree.isPlaceholder).toBe(false)
    const pending = tree.loadRoot()
    expect(tree.loading).toBe(true)
    resolveRoot?.([{ id: 'r', label: 'R' }])
    const roots = await pending
    expect(tree.loading).toBe(false)
    expect(roots.map((node) => node.key)).toEqual(['r'])
    const children = await tree.loadChildren(firstNode(roots))
    expect(children.map((node) => node.key)).toEqual(['r-child'])
    expect(loaded).toEqual(['r'])
  })

  it('③ 选择模型与选择开关', () => {
    const selected: TreeNode[] = []
    const tree = useTreeBase({ data, onSelect: (node) => selected.push(node) })
    tree.select(firstNode(tree.treeData))
    expect(tree.selectedKey).toBe('a')
    expect(selected.map((node) => node.key)).toEqual(['a'])

    const readonlyTree = useTreeBase({ data, selectable: false })
    readonlyTree.select(firstNode(readonlyTree.treeData))
    expect(readonlyTree.selectedKey).toBeUndefined()
  })

  it('④ 勾选级联与 checkStrictly 独立', () => {
    const tree = useTreeBase({ data, checkable: true })
    tree.check('a')
    expect([...tree.checkedKeys].sort()).toEqual(['a', 'a1', 'a2', 'a2x'])
    tree.check('a', false)
    expect(tree.checkedKeys).toEqual([])

    const strict = useTreeBase({ data, checkable: true, checkStrictly: true })
    strict.check('a')
    expect(strict.checkedKeys).toEqual(['a'])
  })

  it('⑤ 过滤保留命中节点及其祖先路径；空关键字全量', () => {
    const tree = useTreeBase({ data })
    const filtered = tree.filterNodes('ax')
    expect(filtered).toHaveLength(1)
    expect(filtered[0]?.key).toBe('a')
    expect(filtered[0]?.children?.[0]?.key).toBe('a2')
    expect(filtered[0]?.children?.[0]?.children?.[0]?.key).toBe('a2x')
    expect(filtered[0]?.children?.[1]).toBeUndefined()

    tree.setKeyword('a1')
    expect(tree.keyword).toBe('a1')
    expect(tree.treeData).toHaveLength(1)
    expect(tree.filterNodes('')).toHaveLength(2)
  })

  it('⑥ defaultExpandAll 与手风琴', () => {
    const tree = useTreeBase({ data, defaultExpandAll: true })
    expect([...tree.expandedKeys].sort()).toEqual(['a', 'a2'])

    const accordion = useTreeBase({ data, accordion: true })
    accordion.toggleExpand('a')
    accordion.toggleExpand('b')
    expect(accordion.expandedKeys).toEqual(['b'])
    accordion.toggleExpand('b')
    expect(accordion.expandedKeys).toEqual([])
  })

  it('⑦ BaseTree 递归渲染 / 事件 / 插槽 / 令牌属性', async () => {
    const wrapper = mountWithPlugins(BaseTree, { props: { data, size: 'large', dataTest: 'tree-x' } })
    expect(wrapper.attributes('data-size')).toBe('large')
    expect(wrapper.attributes('data-test')).toBe('tree-x')
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.text()).toContain('A')

    const firstRow = wrapper.findAll('.bms-tree__row')[0]
    if (firstRow) {
      await firstRow.trigger('click')
    }
    expect(wrapper.emitted('node-click')?.[0]?.[0]).toMatchObject({ key: 'a' })
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ key: 'a' })

    await wrapper.find('.bms-tree__toggle').trigger('click')
    expect(wrapper.emitted('node-expand')?.[0]?.[0]).toMatchObject({ key: 'a' })
    expect(wrapper.findAll('li').length).toBeGreaterThan(2)

    const checkWrapper = mountWithPlugins(BaseTree, { props: { data, checkable: true } })
    await checkWrapper.find('input[type="checkbox"]').setValue(true)
    const checked = checkWrapper.emitted('check')?.[0]?.[0] as string[] | undefined
    expect(checked).toContain('a')
    expect(checked).toContain('a2x')

    const slotWrapper = mountWithPlugins(BaseTree, {
      props: { data },
      slots: {
        default: ({ node }: { node: TreeNode }) => h('b', { class: 'node-label' }, node.label.toLowerCase()),
        actions: '<i class="node-action">·</i>',
      },
    })
    expect(slotWrapper.find('.node-label').text()).toBe('a')
    expect(slotWrapper.findAll('.node-action').length).toBeGreaterThan(0)

    const emptyWrapper = mountWithPlugins(BaseTree, {
      props: { data: [] },
      slots: { empty: '<em class="none">空</em>' },
    })
    expect(emptyWrapper.find('.none').exists()).toBe(true)

    const hidden = mountWithPlugins(BaseTree, { props: { data, visible: false } })
    expect(hidden.find('ul').exists()).toBe(false)
  })

  it('⑧ 自定义归一键透传（nodeKey / labelKey / childrenKey）', () => {
    const customData = [{ id: 'r1', name: '根', nodes: [{ id: 'c1', name: '子' }] }] as unknown as TreeNode[]
    const wrapper = mountWithPlugins(BaseTree, {
      props: {
        data: customData,
        nodeKey: 'id',
        labelKey: 'name',
        childrenKey: 'nodes',
        defaultExpandAll: true,
      },
    })
    expect(wrapper.text()).toContain('根')
    expect(wrapper.text()).toContain('子')
  })
})
