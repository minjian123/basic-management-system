/**
 * 树组件基类（树族）：加载 / 展开与勾选 / 过滤 / 缓存。
 */

import { BaseDataState } from './data-state'

/** 树节点。 */
export interface TreeNode {
  /** 节点键。 */
  key: string
  /** 子节点。 */
  children?: TreeNode[]
}

/** 树组件基类（抽象）。 */
export abstract class BaseTreeData extends BaseDataState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'tree-data'
  /** 节点。 */
  nodes: TreeNode[] = []
  /** 已展开节点键。 */
  readonly expanded = new Set<string>()
  /** 已勾选节点键。 */
  readonly checked = new Set<string>()
  /** 过滤文本。 */
  filterText = ''

  /**
   * 设置节点（整体替换）。
   *
   * @param nodes 节点。
   */
  load(nodes: readonly TreeNode[]): void {
    this.nodes = [...nodes]
  }

  /**
   * 展开 / 收起节点。
   *
   * @param key 节点键。
   * @param expanded 是否展开。
   */
  expand(key: string, expanded = true): void {
    if (expanded) {
      this.expanded.add(key)
    } else {
      this.expanded.delete(key)
    }
  }

  /**
   * 勾选 / 取消勾选节点。
   *
   * @param key 节点键。
   * @param checked 是否勾选。
   */
  check(key: string, checked = true): void {
    if (checked) {
      this.checked.add(key)
    } else {
      this.checked.delete(key)
    }
  }

  /**
   * 设置过滤文本。
   *
   * @param text 过滤文本。
   */
  setFilter(text: string): void {
    this.filterText = text
  }

  /** 过滤后的节点（保留命中的子树）。 */
  get filtered(): TreeNode[] {
    const text = this.filterText.trim()
    if (text === '') {
      return this.nodes
    }
    const filter = (nodes: readonly TreeNode[]): TreeNode[] =>
      nodes.flatMap((node) => {
        const children = node.children === undefined ? [] : filter(node.children)
        if (node.key.includes(text) || children.length > 0) {
          return [children.length > 0 ? { ...node, children } : node]
        }
        return []
      })
    return filter(this.nodes)
  }
}
