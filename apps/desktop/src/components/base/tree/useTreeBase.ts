/**
 * 树域组合式（`useTreeBase`）：树域基类的组合轨。
 *
 * 契约见《组件设计 · 树域基类》：组合 `useTreeData`（归一 / 懒加载 / 选中 / 勾选 / 释放），
 * 补充域层视图态——过滤**保留命中节点及其祖先路径**、手风琴、全展开、选择开关。
 * **占位先行**：未注入 `load` 时为占位（不请求，静态数据或空）。
 * 依赖方向：片段 + Vue；不依赖 UI 库（`el-tree` / Vant 由子类接入）。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { useTreeData, type TreeNode } from '../tree-data/useTreeData'

/** 树域组合式参数 */
export interface UseTreeBaseOptions {
  data?: MaybeRefOrGetter<TreeNode[]>
  /** 远程 / 懒加载：无参取根，传 node 取子级（缺省即占位） */
  load?: (node?: TreeNode) => Promise<unknown[]>
  nodeKey?: string
  labelKey?: string
  childrenKey?: string
  checkable?: MaybeRefOrGetter<boolean>
  checkStrictly?: MaybeRefOrGetter<boolean>
  selectable?: MaybeRefOrGetter<boolean>
  accordion?: MaybeRefOrGetter<boolean>
  filterable?: MaybeRefOrGetter<boolean>
  defaultExpandAll?: boolean
  onSelect?: (node: TreeNode) => void
  onCheck?: (checkedKeys: string[]) => void
  onLoaded?: (node: TreeNode) => void
}

/** 树域组合式返回值 */
export interface UseTreeBaseReturn {
  /** 过滤态（`keyword` 非空）或全量树数据 */
  readonly treeData: TreeNode[]
  readonly loading: boolean
  readonly isPlaceholder: boolean
  readonly selectedKey: string | undefined
  readonly checkedKeys: string[]
  readonly expandedKeys: string[]
  readonly keyword: string
  setKeyword: (keyword: string) => void
  select: (node: TreeNode) => void
  check: (key: string, checked?: boolean) => void
  toggleExpand: (key: string) => void
  loadRoot: (params?: Record<string, unknown>) => Promise<TreeNode[]>
  loadChildren: (node: TreeNode) => Promise<TreeNode[]>
  /** 过滤（保留命中节点及其祖先路径；空关键字返回全量） */
  filterNodes: (keyword: string) => TreeNode[]
}

/**
 * 获取树域能力。
 *
 * 用法：`const tree = useTreeBase({ load, checkable: true, onSelect })`；
 * 省略 `load` 即得占位行为（只展示静态数据）。
 */
export function useTreeBase(options: UseTreeBaseOptions = {}): UseTreeBaseReturn {
  const load = options.load
  const tree = useTreeData({
    ...(options.data !== undefined ? { data: options.data } : {}),
    ...(load ? { loader: () => load(), childLoader: (node: TreeNode) => load(node) } : {}),
    ...(options.nodeKey !== undefined ? { nodeKey: options.nodeKey } : {}),
    ...(options.labelKey !== undefined ? { labelKey: options.labelKey } : {}),
    ...(options.childrenKey !== undefined ? { childrenKey: options.childrenKey } : {}),
    ...(options.checkable !== undefined ? { checkable: options.checkable } : {}),
    ...(options.checkStrictly !== undefined ? { checkStrictly: options.checkStrictly } : {}),
    lazy: load !== undefined,
  })

  const keyword = ref('')

  const eachNode = (
    nodes: TreeNode[],
    visit: (node: TreeNode, parentKey: string | undefined) => void,
    parentKey?: string,
  ): void => {
    for (const node of nodes) {
      visit(node, parentKey)
      if (node.children) {
        eachNode(node.children, visit, node.key)
      }
    }
  }

  const prune = (nodes: TreeNode[], lower: string): TreeNode[] => {
    const result: TreeNode[] = []
    for (const node of nodes) {
      const children = node.children ? prune(node.children, lower) : []
      const hit = node.label.toLowerCase().includes(lower)
      if (hit || children.length > 0) {
        const next: TreeNode = { ...node }
        if (children.length > 0) {
          next.children = children
        } else {
          delete next.children
        }
        result.push(next)
      }
    }
    return result
  }

  const findNode = (nodes: TreeNode[], key: string): TreeNode | undefined => {
    for (const node of nodes) {
      if (node.key === key) {
        return node
      }
      const found = node.children ? findNode(node.children, key) : undefined
      if (found) {
        return found
      }
    }
    return undefined
  }

  const findParentKey = (key: string): string | undefined => {
    let parentKey: string | undefined
    eachNode(tree.treeData, (node, parent) => {
      if (node.key === key) {
        parentKey = parent
      }
    })
    return parentKey
  }

  const expandNode = (node: TreeNode): void => {
    if ((node.children?.length ?? 0) > 0 && !tree.expandedKeys.includes(node.key)) {
      tree.toggleExpand(node.key)
    }
  }

  const expandAllLoaded = (): void => {
    eachNode(tree.treeData, (node) => {
      expandNode(node)
    })
  }

  const selectable = computed(() => options.selectable === undefined || Boolean(toValue(options.selectable)))
  const filtered = computed(() => {
    const lower = keyword.value.trim().toLowerCase()
    if (!lower) {
      return tree.treeData
    }
    return prune(tree.treeData, lower)
  })

  const loadRoot = async (params?: Record<string, unknown>): Promise<TreeNode[]> => {
    const roots = await tree.loadRoot(params)
    if (options.defaultExpandAll) {
      expandAllLoaded()
    }
    return roots
  }

  const loadChildren = async (node: TreeNode): Promise<TreeNode[]> => {
    const children = await tree.loadChildren(node)
    if (options.defaultExpandAll) {
      for (const child of children) {
        expandNode(child)
      }
    }
    options.onLoaded?.(node)
    return children
  }

  const select = (node: TreeNode): void => {
    if (!selectable.value) {
      return
    }
    tree.select(node.key)
    options.onSelect?.(node)
  }

  const check = (key: string, checked = true): void => {
    tree.check(key, checked)
    options.onCheck?.([...tree.checkedKeys])
  }

  const toggleExpand = (key: string): void => {
    const isExpanded = tree.expandedKeys.includes(key)
    if (Boolean(toValue(options.accordion)) && !isExpanded) {
      const parentKey = findParentKey(key)
      const siblings = parentKey ? (findNode(tree.treeData, parentKey)?.children ?? []) : tree.treeData
      for (const sibling of siblings) {
        if (sibling.key !== key && tree.expandedKeys.includes(sibling.key)) {
          tree.toggleExpand(sibling.key)
        }
      }
    }
    tree.toggleExpand(key)
  }

  if (options.defaultExpandAll) {
    expandAllLoaded()
  }

  return {
    get treeData() {
      return filtered.value
    },
    get loading() {
      return tree.loading
    },
    get isPlaceholder() {
      return tree.isPlaceholder
    },
    get selectedKey() {
      return tree.selectedKey
    },
    get checkedKeys() {
      return tree.checkedKeys
    },
    get expandedKeys() {
      return tree.expandedKeys
    },
    get keyword() {
      return keyword.value
    },
    setKeyword: (value: string) => {
      keyword.value = value
    },
    select,
    check,
    toggleExpand,
    loadRoot,
    loadChildren,
    filterNodes: (value: string) => {
      const lower = value.trim().toLowerCase()
      if (!lower) {
        return tree.treeData
      }
      return prune(tree.treeData, lower)
    },
  }
}
