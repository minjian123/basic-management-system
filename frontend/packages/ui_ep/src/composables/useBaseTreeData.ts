/** 树数据投影：把核心树组件基类 `BaseTreeData` 投影为组合式（节点 / 数据状态 / 过滤 / 展开）。 */

import { BaseTreeData, type TreeNode } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体树件（可实例化）。 */
class TreeState extends BaseTreeData {}

/** 选项。 */
export interface UseBaseTreeDataOptions {
  /** 初始节点。 */
  nodes?: readonly TreeNode[]
  /** 初始过滤文本。 */
  filterText?: string
}

/** `useBaseTreeData` 返回面。 */
export interface UseBaseTreeDataResult {
  /** 树基类实例。 */
  tree: BaseTreeData
  /** 节点（响应式）。 */
  nodes: Ref<TreeNode[]>
  /** 过滤文本（响应式）。 */
  filterText: Ref<string>
  /** 数据状态（`loading` / `ready` / `empty` / `error`）。 */
  state: Ref<string>
  /** 设置节点（并按空否结算状态）。 */
  setNodes: (nodes: readonly TreeNode[]) => void
  /** 设置过滤文本。 */
  setFilterText: (text: string) => void
  /** 展开 / 收起。 */
  setExpanded: (key: string, expanded?: boolean) => void
  /** 勾选 / 取消勾选。 */
  setChecked: (key: string, checked?: boolean) => void
}

/**
 * 使用树数据投影。
 *
 * @param options 选项。
 * @returns 树基类实例与响应式面。
 */
export function useBaseTreeData(options: UseBaseTreeDataOptions = {}): UseBaseTreeDataResult {
  const tree = new TreeState()
  if (options.nodes !== undefined) {
    tree.load(options.nodes)
  }
  if (options.filterText !== undefined) {
    tree.filterText = options.filterText
  }

  const nodes = ref<TreeNode[]>(tree.nodes)
  const filterText = ref(tree.filterText)
  const state = ref<string>(tree.state)
  tree.onStateChange((next) => {
    state.value = next
  })
  const off = tree.onLifecycle((event) => {
    if (event === 'update') {
      nodes.value = tree.nodes
      filterText.value = tree.filterText
    }
  })
  onScopeDispose(off)

  function setNodes(next: readonly TreeNode[]): void {
    tree.load(next)
    const token = tree.begin()
    tree.settle(token, tree.nodes.length === 0 ? 'empty' : 'ready')
  }

  return {
    tree,
    nodes,
    filterText,
    state,
    setNodes,
    setFilterText: (text) => {
      tree.filterText = text
      tree.notifyLifecycle('update')
    },
    setExpanded: (key, expanded = true) => {
      tree.expand(key, expanded)
      tree.notifyLifecycle('update')
    },
    setChecked: (key, checked = true) => {
      tree.check(key, checked)
      tree.notifyLifecycle('update')
    },
  }
}
