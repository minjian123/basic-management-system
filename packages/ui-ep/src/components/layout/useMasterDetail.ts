/**
 * 树形主从状态（组件级组合式，非能力片段）：选中 / 展开 / 比例 / 折叠 / 窄屏抽屉。
 *
 * 契约见《组件设计 · 树形主从布局》§2 / §3；分割比例与折叠状态经 `usePersistedState`
 * 持久化（用户偏好；远端同步随后端偏好接入）。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'

import { usePersistedState } from '@bms/vue'

/** 树节点（与 `useTreeData` 契约对齐） */
export interface TreeNode {
  id: string
  parentId?: string
  label: string
  children?: TreeNode[]
  /** 懒加载叶子标记 */
  leaf?: boolean
  /** 节点记录数（`showCount` 展示） */
  count?: number
}

export interface UseMasterDetailOptions {
  /** 比例 / 折叠持久化键（缺省不持久化） */
  splitStorageKey?: string
  /** 初始主区占比（0.2 ~ 0.6，缺省 0.3） */
  defaultRatio?: number
  collapsible?: boolean
}

export interface UseMasterDetailReturn {
  selectedKeys: Ref<string[]>
  selectedNodes: Ref<TreeNode[]>
  selectedNode: ComputedRef<TreeNode | null>
  expandedKeys: Ref<string[]>
  /** 主区占比（0.2 ~ 0.6） */
  ratio: Ref<number>
  collapsed: Ref<boolean>
  drawerVisible: Ref<boolean>
  select: (node: TreeNode | null) => void
  setCheckedNodes: (nodes: TreeNode[]) => void
  toggleCollapse: () => void
  setCollapsed: (value: boolean) => void
  openDrawer: () => void
  closeDrawer: () => void
  setRatio: (next: number) => void
  setExpandedKeys: (keys: string[]) => void
}

const RATIO_MIN = 0.2
const RATIO_MAX = 0.6

function clampRatio(value: number, fallback: number): number {
  if (!Number.isFinite(value)) {
    return fallback
  }
  return Math.min(RATIO_MAX, Math.max(RATIO_MIN, value))
}

/**
 * 获取树形主从状态能力。
 *
 * 用法：`const master = useMasterDetail({ splitStorageKey: 'user' })`，绑定布局与选中回调。
 */
export function useMasterDetail(options: UseMasterDetailOptions = {}): UseMasterDetailReturn {
  const defaultRatio = clampRatio(options.defaultRatio ?? 0.3, 0.3)
  const persistKey = options.splitStorageKey?.trim() ?? ''

  const ratioStore = persistKey
    ? usePersistedState<number>({ key: `${persistKey}:ratio`, defaultValue: defaultRatio })
    : null
  const collapsedStore = persistKey
    ? usePersistedState<boolean>({ key: `${persistKey}:collapsed`, defaultValue: false })
    : null

  const ratio = ref(clampRatio((ratioStore?.get() as number | undefined) ?? defaultRatio, defaultRatio))
  const collapsed = ref(Boolean(collapsedStore?.get() ?? false))
  const selectedKeys = ref<string[]>([])
  const selectedNodes = ref<TreeNode[]>([])
  const selectedNode = computed(() => selectedNodes.value[0] ?? null)
  const expandedKeys = ref<string[]>([])
  const drawerVisible = ref(false)

  function select(node: TreeNode | null): void {
    if (node) {
      selectedKeys.value = [node.id]
      selectedNodes.value = [node]
      return
    }
    selectedKeys.value = []
    selectedNodes.value = []
  }

  function setCheckedNodes(nodes: TreeNode[]): void {
    selectedNodes.value = [...nodes]
    selectedKeys.value = nodes.map((node) => node.id)
  }

  function setCollapsed(value: boolean): void {
    collapsed.value = value
    collapsedStore?.set(value)
  }

  function toggleCollapse(): void {
    setCollapsed(!collapsed.value)
  }

  function setRatio(next: number): void {
    ratio.value = clampRatio(next, ratio.value)
    ratioStore?.set(ratio.value)
  }

  return {
    selectedKeys,
    selectedNodes,
    selectedNode,
    expandedKeys,
    ratio,
    collapsed,
    drawerVisible,
    select,
    setCheckedNodes,
    toggleCollapse,
    setCollapsed,
    openDrawer: () => {
      drawerVisible.value = true
    },
    closeDrawer: () => {
      drawerVisible.value = false
    },
    setRatio,
    setExpandedKeys: (keys: string[]) => {
      expandedKeys.value = [...keys]
    },
  }
}
