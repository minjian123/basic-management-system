/**
 * 字典树：把平铺字典条目（`DictItem[]`，含 `parentId`）组装为树节点。
 *
 * 与平铺字典选择（`dict_select`）同一数据源 / 同一缓存，只是展示形态不同：
 * 平铺件按 `parentId` 过滤当前层，树件一次组装全量层级。
 * 纯函数、不触 DOM / 请求 / 框架，便于单测与跨端复用。
 */

import type { DictItem } from './dict'

/** 字典树节点（与 `DictSelectField` 的 `DictItem` 同源，仅保留树展示所需字段）。 */
export interface DictTreeSelectNode {
  /** 节点键（字典条目 id）。 */
  key: string
  /** 展示文案。 */
  label: string
  /** 是否禁用（条目状态非 `enabled`）。 */
  disabled?: boolean
  /** 子节点（无子节点时不带该字段）。 */
  children?: DictTreeSelectNode[]
}

/** 组树选项。 */
export interface BuildDictTreeOptions {
  /** 根节点的父标识（缺省 `'0'`，兼容 `parentId` 缺省即顶层）。 */
  rootParentId?: string
  /** 孤儿节点（父不存在）是否挂到根：真挂根、假丢弃（缺省挂根，避免静默丢数据）。 */
  keepOrphans?: boolean
}

/** 顶层父标识：字典接口里 `'0'` 表示顶层；条目 `parentId` 缺省也视为顶层。 */
const TOP_PARENT = '0'

/**
 * 同级排序：先 `sort` 升序，`sort` 相同按文案。
 *
 * @param items 条目集。
 * @returns DictItem[]: 排序后的新数组。
 */
function ordered(items: readonly DictItem[]): DictItem[] {
  return [...items].sort((left, right) => left.sort - right.sort || left.label.localeCompare(right.label))
}

/**
 * 组装字典树。
 *
 * @param items 平铺字典条目。
 * @param options 组树选项。
 * @returns DictTreeSelectNode[]: 根节点集合。
 */
export function buildDictTree(items: readonly DictItem[], options: BuildDictTreeOptions = {}): DictTreeSelectNode[] {
  const rootParentId = options.rootParentId ?? TOP_PARENT
  const keepOrphans = options.keepOrphans ?? true
  const byParent = new Map<string, DictItem[]>()

  for (const item of items) {
    const parent = item.parentId === undefined || item.parentId === '' ? rootParentId : item.parentId
    const bucket = byParent.get(parent)
    if (bucket === undefined) {
      byParent.set(parent, [item])
    } else {
      bucket.push(item)
    }
  }

  const visited = new Set<string>()

  const buildNode = (item: DictItem): DictTreeSelectNode => {
    visited.add(item.id)
    const children = ordered(byParent.get(item.id) ?? [])
      .filter((child) => !visited.has(child.id))
      .map(buildNode)
    const node: DictTreeSelectNode = { key: item.id, label: item.label }
    if (item.status !== 'enabled') {
      node.disabled = true
    }
    if (children.length > 0) {
      node.children = children
    }
    return node
  }

  const roots = ordered(byParent.get(rootParentId) ?? []).map(buildNode)
  if (keepOrphans) {
    // 父不存在的节点（含环）挂根：逐个判重——前一个孤儿递归时可能已带走后续节点。
    for (const item of ordered(items)) {
      if (!visited.has(item.id)) {
        roots.push(buildNode(item))
      }
    }
  }
  return roots
}

/**
 * 在已组装树中查找节点路径（用于只读态回显）。
 *
 * @param nodes 根节点集合。
 * @param key 目标节点键。
 * @returns DictTreeSelectNode[]: 从根到目标的路径（未命中空数组）。
 */
export function findDictTreePath(nodes: readonly DictTreeSelectNode[], key: string): DictTreeSelectNode[] {
  const path: DictTreeSelectNode[] = []
  const walk = (current: readonly DictTreeSelectNode[]): boolean => {
    for (const node of current) {
      path.push(node)
      if (node.key === key) {
        return true
      }
      if (node.children !== undefined && walk(node.children)) {
        return true
      }
      path.pop()
    }
    return false
  }
  return walk(nodes) ? path : []
}
