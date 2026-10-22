/**
 * 菜单树纯函数（框架无关）：扁平化 / 过滤 / 展开策略 / 拖拽调序 → `parent_id` + `sort` 计算。
 *
 * 口径（《03_03_01 详细设计》§6.2 / §6.3）：
 * - 菜单树只有**目录**（无视图组件）与**菜单**（有视图组件）两类，按钮为独立实体不在树内；
 * - 拖拽落位：`before` / `after`＝同级并排前 / 后（跨父级即改 `parent_id`），`inner`＝成为目标子级
 *   （**仅目录**可容纳下级）；禁止拖入自身子树；
 * - 同级 `sort` 按 10 / 20 / 30… 重排，只把**父级或顺序发生变化**的节点计入提交清单。
 */

import type { MenuItem } from '@/api/menuMeta'

/** 拖拽落位。 */
export type DropPosition = 'before' | 'after' | 'inner'

/**
 * 取子节点清单（契约 `children` 为可选，缺省按空树处理）。
 *
 * @param node 菜单节点。
 * @returns 子节点清单（恒为数组）。
 */
function childrenOf(node: MenuItem): MenuItem[] {
  return node.children ?? []
}

/** 节点排序变更（提交 `PUT /menus/{id}` 的最小依据）。 */
export interface MenuMove {
  /** 菜单主键。 */
  id: string
  /** 新父级 ID（`0` 为根）。 */
  parent_id: string
  /** 新排序值。 */
  sort: number
}

/** 拖拽调序结果。 */
export interface MenuReorderResult {
  /** 需提交的变更节点（无变更时为空数组）。 */
  moves: MenuMove[]
  /** 乐观更新后的树。 */
  tree: MenuItem[]
}

/** 列表筛选条件。 */
export interface MenuFilter {
  /** 关键字（菜单名称 / 路由路径，不区分大小写）。 */
  keyword?: string
  /** 菜单类型（空 = 全部）。 */
  type?: '' | 'directory' | 'menu'
  /** 状态（空 = 全部）。 */
  status?: '' | 'enabled' | 'disabled'
}

/** 树形选择项（父级下拉）。 */
export interface MenuTreeOption {
  /** 值（菜单 ID，根为 `0`）。 */
  id: string
  /** 显示名。 */
  label: string
  /** 子项。 */
  children?: MenuTreeOption[]
}

/** 平铺选择项（关联菜单多选）。 */
export interface MenuFlatOption {
  /** 值（菜单 ID）。 */
  id: string
  /** 显示名（含层级路径）。 */
  label: string
}

/**
 * 是否目录节点（无视图组件）。
 *
 * @param node 菜单节点。
 * @returns 是否目录。
 */
export function isDirectory(node: MenuItem): boolean {
  return node.component === null || node.component === ''
}

/**
 * 菜单类型。
 *
 * @param node 菜单节点。
 * @returns `directory` / `menu`。
 */
export function menuTypeOf(node: MenuItem): 'directory' | 'menu' {
  return isDirectory(node) ? 'directory' : 'menu'
}

/**
 * 深拷贝菜单树（只保留契约字段，避免把响应式代理带进纯函数结果）。
 *
 * @param nodes 菜单树。
 * @returns 拷贝结果。
 */
export function cloneMenus(nodes: readonly MenuItem[]): MenuItem[] {
  return nodes.map((node) => ({ ...node, children: cloneMenus(childrenOf(node)) }))
}

/**
 * 按 ID 查找节点。
 *
 * @param nodes 菜单树。
 * @param id 菜单主键。
 * @returns 命中节点；未命中返回 `undefined`。
 */
export function findMenu(nodes: readonly MenuItem[], id: string): MenuItem | undefined {
  for (const node of nodes) {
    if (node.id === id) {
      return node
    }
    const hit = findMenu(childrenOf(node), id)
    if (hit !== undefined) {
      return hit
    }
  }
  return undefined
}

/**
 * 取节点自身及全部后代 ID。
 *
 * @param node 菜单节点。
 * @returns ID 集合。
 */
export function subtreeIds(node: MenuItem): Set<string> {
  const ids = new Set<string>()
  const walk = (item: MenuItem): void => {
    ids.add(item.id)
    for (const child of childrenOf(item)) {
      walk(child)
    }
  }
  walk(node)
  return ids
}

/**
 * 先序平铺菜单树。
 *
 * @param nodes 菜单树。
 * @returns 平铺节点清单。
 */
export function flattenMenus(nodes: readonly MenuItem[]): MenuItem[] {
  const result: MenuItem[] = []
  for (const node of nodes) {
    result.push(node)
    result.push(...flattenMenus(childrenOf(node)))
  }
  return result
}

/**
 * 统计节点总数。
 *
 * @param nodes 菜单树。
 * @returns 节点数。
 */
export function countMenus(nodes: readonly MenuItem[]): number {
  let total = 0
  for (const node of nodes) {
    total += 1 + countMenus(childrenOf(node))
  }
  return total
}

/**
 * 全部可展开节点 ID（有子节点者）。
 *
 * @param nodes 菜单树。
 * @returns 可展开 ID 清单（先序）。
 */
export function expandableIds(nodes: readonly MenuItem[]): string[] {
  const ids: string[] = []
  for (const node of nodes) {
    if (childrenOf(node).length > 0) {
      ids.push(node.id)
    }
    ids.push(...expandableIds(childrenOf(node)))
  }
  return ids
}

/**
 * 第一层可展开节点 ID。
 *
 * @param nodes 菜单树。
 * @returns 第一层可展开 ID 清单。
 */
export function firstLevelExpandableIds(nodes: readonly MenuItem[]): string[] {
  return nodes.filter((node) => childrenOf(node).length > 0).map((node) => node.id)
}

/**
 * 关键字命中路径的展开 ID（命中节点及其祖先；临时展开不写偏好）。
 *
 * @param nodes 菜单树。
 * @param keyword 关键字（空串返回空清单）。
 * @returns 可展开 ID 清单。
 */
export function expandIdsForKeyword(nodes: readonly MenuItem[], keyword: string): string[] {
  const needle = keyword.trim().toLowerCase()
  if (needle === '') {
    return []
  }
  const matched = new Set<string>()
  const walk = (list: readonly MenuItem[]): boolean => {
    let found = false
    for (const node of list) {
      const selfMatch =
        node.name.toLowerCase().includes(needle) || node.path.toLowerCase().includes(needle)
      const childMatch = walk(childrenOf(node))
      if (selfMatch || childMatch) {
        matched.add(node.id)
      }
      found = found || selfMatch || childMatch
    }
    return found
  }
  walk(nodes)
  return expandableIds(nodes).filter((id) => matched.has(id))
}

/**
 * 树过滤（保留命中节点的祖先链；关键字匹配名称 / 路径）。
 *
 * @param nodes 菜单树。
 * @param filter 筛选条件。
 * @returns 过滤后的树（新对象，不修改入参）。
 */
export function filterMenus(nodes: readonly MenuItem[], filter: MenuFilter): MenuItem[] {
  const needle = (filter.keyword ?? '').trim().toLowerCase()
  const filterType = filter.type ?? ''
  const filterStatus = filter.status ?? ''
  const walk = (list: readonly MenuItem[]): MenuItem[] => {
    const result: MenuItem[] = []
    for (const node of list) {
      const children = walk(childrenOf(node))
      const keywordMatch =
        needle === '' ||
        node.name.toLowerCase().includes(needle) ||
        node.path.toLowerCase().includes(needle)
      const typeMatch = filterType === '' || menuTypeOf(node) === filterType
      const statusMatch = filterStatus === '' || node.status === filterStatus
      if ((keywordMatch && typeMatch && statusMatch) || children.length > 0) {
        result.push({ ...node, children })
      }
    }
    return result
  }
  return walk(nodes)
}

/**
 * 取同父级下的下一个排序值（`(最大 sort) + 10`）。
 *
 * @param nodes 菜单树。
 * @param parentId 父级 ID（`0` 为根）。
 * @returns 下一个排序值。
 */
export function nextSort(nodes: readonly MenuItem[], parentId: string): number {
  const siblings =
    parentId === '0' ? nodes : (findMenu(nodes, parentId)?.children ?? [])
  const max = siblings.reduce((value, node) => Math.max(value, node.sort), 0)
  return max + 10
}

/**
 * 拖拽调序（本地乐观更新 + 最小提交清单）。
 *
 * @param nodes 当前菜单树。
 * @param dragId 被拖节点 ID。
 * @param dropId 目标节点 ID。
 * @param position 落位（前 / 后 / 成为子级）。
 * @returns 结果；非法落位（拖自身 / 拖入自身子树 / 拖入菜单而非目录 / 节点不存在）返回 `undefined`。
 */
export function reorderMenus(
  nodes: readonly MenuItem[],
  dragId: string,
  dropId: string,
  position: DropPosition,
): MenuReorderResult | undefined {
  if (dragId === dropId) {
    return undefined
  }
  const tree = cloneMenus(nodes)
  const drag = findMenu(tree, dragId)
  if (drag === undefined || findMenu(tree, dropId) === undefined) {
    return undefined
  }
  if (subtreeIds(drag).has(dropId)) {
    return undefined
  }
  const target = findMenu(tree, dropId) as MenuItem
  if (position === 'inner' && !isDirectory(target)) {
    return undefined
  }

  // 先从原父级摘除（保留被拖节点自身子树）
  const detach = (list: MenuItem[], id: string): boolean => {
    const index = list.findIndex((node) => node.id === id)
    if (index >= 0) {
      list.splice(index, 1)
      return true
    }
    return list.some((node) => detach(childrenOf(node), id))
  }
  detach(tree, dragId)

  if (position === 'inner') {
    target.children = [...childrenOf(target), drag]
  } else {
    const siblings = target.parent_id === '0' ? tree : (findMenu(tree, target.parent_id)?.children ?? [])
    const index = siblings.findIndex((node) => node.id === dropId)
    siblings.splice(position === 'before' ? index : index + 1, 0, drag)
  }

  const moves: MenuMove[] = []
  const renumber = (list: MenuItem[], parentId: string): void => {
    list.forEach((node, index) => {
      const sort = (index + 1) * 10
      if (node.parent_id !== parentId || node.sort !== sort) {
        moves.push({ id: node.id, parent_id: parentId, sort })
      }
      node.parent_id = parentId
      node.sort = sort
      renumber(childrenOf(node), node.id)
    })
  }
  renumber(tree, '0')
  return { moves, tree }
}

/**
 * 父级下拉树选项（含「（根级）」；排除自身与自身子树）。
 *
 * @param nodes 菜单树。
 * @param excludeId 需排除的节点 ID（编辑态传当前节点）。
 * @returns 树形选项。
 */
export function toMenuTreeOptions(nodes: readonly MenuItem[], excludeId?: string): MenuTreeOption[] {
  const excluded = new Set<string>()
  if (excludeId !== undefined) {
    const node = findMenu(nodes, excludeId)
    if (node !== undefined) {
      for (const id of subtreeIds(node)) {
        excluded.add(id)
      }
    }
  }
  const walk = (list: readonly MenuItem[]): MenuTreeOption[] =>
    list
      .filter((node) => !excluded.has(node.id))
      .map((node) => {
        const children = walk(childrenOf(node))
        return children.length > 0
          ? { id: node.id, label: node.name, children }
          : { id: node.id, label: node.name }
      })
  return [{ id: '0', label: '（根级）' }, ...walk(nodes)]
}

/**
 * 平铺菜单选项（关联菜单多选；标签含层级路径）。
 *
 * @param nodes 菜单树。
 * @returns 平铺选项。
 */
export function toMenuFlatOptions(nodes: readonly MenuItem[]): MenuFlatOption[] {
  const result: MenuFlatOption[] = []
  const walk = (list: readonly MenuItem[], prefix: string): void => {
    for (const node of list) {
      const label = prefix === '' ? node.name : `${prefix} / ${node.name}`
      result.push({ id: node.id, label })
      walk(childrenOf(node), label)
    }
  }
  walk(nodes, '')
  return result
}
