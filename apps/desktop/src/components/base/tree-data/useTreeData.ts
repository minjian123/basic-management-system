/**
 * 树数据片段（`tree-data`）：树形数据的加载、懒加载、选中与过滤。
 *
 * 契约见《组件设计 · 树数据片段》：`loadRoot` / `loadChildren`（懒加载）/ 选中与勾选 /
 * `normalize`（树选择、组织树、权限树、树形主从共用；归 `BaseTree` 域基类消费）。
 * **占位先行**：未注入 `loader`（后端组织 / 字典树未接入）时 `loadRoot` 返回静态数据或空数组，不发请求。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 树节点（原始数据由 `normalize` 归一为统一形状） */
export interface TreeNode {
  key: string
  label: string
  raw?: unknown
  disabled?: boolean
  isLeaf?: boolean
  children?: TreeNode[]
}

/** 树数据片段参数 */
export interface UseTreeDataOptions {
  /** 静态树数据（占位与本地数据） */
  data?: MaybeRefOrGetter<TreeNode[]>
  /** 根节点加载器（缺省即占位：不请求） */
  loader?: (params?: Record<string, unknown>) => Promise<unknown[]>
  /** 子节点加载器（懒加载；缺省时按一次性数据展开） */
  childLoader?: (node: TreeNode) => Promise<unknown[]>
  nodeKey?: string
  labelKey?: string
  childrenKey?: string
  checkable?: MaybeRefOrGetter<boolean>
  /** 勾选是否严格（父子不联动） */
  checkStrictly?: MaybeRefOrGetter<boolean>
  lazy?: MaybeRefOrGetter<boolean>
}

/** 树数据片段返回值 */
export interface UseTreeDataReturn {
  readonly treeData: TreeNode[]
  readonly loading: boolean
  readonly isPlaceholder: boolean
  readonly selectedKey: string | undefined
  readonly selectedKeys: string[]
  readonly checkedKeys: string[]
  readonly expandedKeys: string[]
  loadRoot: (params?: Record<string, unknown>) => Promise<TreeNode[]>
  loadChildren: (node: TreeNode) => Promise<TreeNode[]>
  normalize: (raw: unknown[]) => TreeNode[]
  select: (key: string, multiple?: boolean) => void
  check: (key: string, checked?: boolean) => void
  toggleExpand: (key: string) => void
  filter: (keyword: string) => TreeNode[]
}

/** 默认归一：`key` / `label` / `children` 三键可配置 */
export function normalizeTree(
  raw: unknown[],
  nodeKey = 'key',
  labelKey = 'label',
  childrenKey = 'children',
): TreeNode[] {
  return raw.map((item) => {
    const record = item as Record<string, unknown>
    const children = Array.isArray(record[childrenKey])
      ? normalizeTree(record[childrenKey] as unknown[], nodeKey, labelKey, childrenKey)
      : undefined
    return {
      key: String(record[nodeKey] ?? record.key ?? ''),
      label: String(record[labelKey] ?? record.label ?? ''),
      raw: item,
      ...(record.disabled === true ? { disabled: true } : {}),
      ...(record.isLeaf === true ? { isLeaf: true } : {}),
      ...(children && children.length > 0 ? { children } : {}),
    }
  })
}

/** 递归遍历（含子级） */
function walk(nodes: TreeNode[], visit: (node: TreeNode) => void): void {
  for (const node of nodes) {
    visit(node)
    if (node.children) {
      walk(node.children, visit)
    }
  }
}

/**
 * 获取树数据能力。
 *
 * 用法：`const tree = useTreeData({ loader, childLoader, lazy: true })`；
 * 后端未就绪时省略两个 loader 即得占位行为（只展示静态数据）。
 */
export function useTreeData(options: UseTreeDataOptions = {}): UseTreeDataReturn {
  const capability = declareFragment('tree-data')

  const rootData = ref<TreeNode[]>([])
  const loading = ref(false)
  const selectedKeys = ref<string[]>([])
  const checkedKeys = ref<string[]>([])
  const expandedKeys = ref<string[]>([])
  const isPlaceholder = computed(() => options.loader === undefined)

  const staticData = computed(() => toValue(options.data) ?? [])
  const normalizedStatic = computed(() =>
    normalizeTree(staticData.value, options.nodeKey, options.labelKey, options.childrenKey),
  )
  const treeData = computed(() => (normalizedStatic.value.length > 0 ? normalizedStatic.value : rootData.value))

  const normalize = (raw: unknown[]): TreeNode[] =>
    normalizeTree(raw, options.nodeKey, options.labelKey, options.childrenKey)

  const loadRoot = async (params?: Record<string, unknown>): Promise<TreeNode[]> => {
    if (!options.loader) {
      capability.log('debug', 'tree-data 占位：根数据加载器未接入，返回静态数据')
      return normalizedStatic.value
    }
    loading.value = true
    try {
      rootData.value = normalize(await options.loader(params))
      return rootData.value
    } finally {
      loading.value = false
    }
  }

  const loadChildren = async (node: TreeNode): Promise<TreeNode[]> => {
    if (!options.childLoader) {
      return node.children ?? []
    }
    loading.value = true
    try {
      const children = normalize(await options.childLoader(node))
      rootData.value = rootData.value.map((item) => (item.key === node.key ? { ...item, children } : item))
      return children
    } finally {
      loading.value = false
    }
  }

  return {
    get treeData() {
      return treeData.value
    },
    get loading() {
      return loading.value
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get selectedKey() {
      return selectedKeys.value[0]
    },
    get selectedKeys() {
      return [...selectedKeys.value]
    },
    get checkedKeys() {
      return [...checkedKeys.value]
    },
    get expandedKeys() {
      return [...expandedKeys.value]
    },
    loadRoot,
    loadChildren,
    normalize,
    select: (key, multiple = false) => {
      if (multiple) {
        selectedKeys.value = selectedKeys.value.includes(key)
          ? selectedKeys.value.filter((item) => item !== key)
          : [...selectedKeys.value, key]
        return
      }
      selectedKeys.value = [key]
    },
    check: (key, checked = true) => {
      const strict = Boolean(toValue(options.checkStrictly))
      const next = new Set(checkedKeys.value)
      if (checked) {
        next.add(key)
      } else {
        next.delete(key)
      }
      if (!strict) {
        walk(treeData.value, (node) => {
          if (node.key === key) {
            const descendants: TreeNode[] = []
            walk(node.children ?? [], (child) => descendants.push(child))
            for (const child of descendants) {
              if (checked) {
                next.add(child.key)
              } else {
                next.delete(child.key)
              }
            }
          }
        })
      }
      checkedKeys.value = [...next]
    },
    toggleExpand: (key) => {
      expandedKeys.value = expandedKeys.value.includes(key)
        ? expandedKeys.value.filter((item) => item !== key)
        : [...expandedKeys.value, key]
    },
    filter: (keyword) => {
      const lower = keyword.trim().toLowerCase()
      if (!lower) {
        return treeData.value
      }
      const matched: TreeNode[] = []
      walk(treeData.value, (node) => {
        if (node.label.toLowerCase().includes(lower)) {
          matched.push(node)
        }
      })
      return matched
    },
  }
}
