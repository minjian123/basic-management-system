/**
 * 领域纯函数：菜单树（后端按权限下发）的过滤 / 扁平化 / 查找 / 转路由节点。
 */

import type { RouteNode } from '../capabilities/dynamic-routes'

/** 菜单节点。 */
export interface MenuNode {
  /** 路由路径（唯一）。 */
  path: string
  /** 标题。 */
  title: string
  /** 路由名（缺省用路径）。 */
  name?: string
  /** 图标名。 */
  icon?: string
  /** 徽标。 */
  badge?: string | number
  /** 权限码（缺省视为公开）。 */
  permission?: string
  /** 子节点。 */
  children?: MenuNode[]
}

/**
 * 按权限过滤菜单树（子节点全被剔除且自身无权限的空父节点一并剔除）。
 *
 * @param menu 菜单树。
 * @param can 权限判定。
 * @returns 过滤后的菜单树。
 */
export function filterMenuByPermission(menu: readonly MenuNode[], can: (code: string) => boolean): MenuNode[] {
  const result: MenuNode[] = []
  for (const node of menu) {
    const allowed = node.permission === undefined || can(node.permission)
    if (node.children !== undefined) {
      const children = filterMenuByPermission(node.children, can)
      if (children.length > 0) {
        result.push({ ...node, children })
      } else if (allowed && node.permission !== undefined) {
        result.push({ ...node, children: [] })
      }
    } else if (allowed) {
      result.push({ ...node })
    }
  }
  return result
}

/**
 * 按关键词过滤菜单树（标题或路径命中；命中节点保留其祖先链、父节点命中保留整棵子树）。
 *
 * @param menu 菜单树。
 * @param keyword 关键词（空串返回原树）。
 * @returns 过滤后的菜单树。
 */
export function filterMenuByKeyword(menu: readonly MenuNode[], keyword: string): MenuNode[] {
  const query = keyword.trim().toLowerCase()
  if (query === '') {
    return [...menu]
  }
  const walk = (nodes: readonly MenuNode[]): MenuNode[] => {
    const result: MenuNode[] = []
    for (const node of nodes) {
      const hit = node.title.toLowerCase().includes(query) || node.path.toLowerCase().includes(query)
      if (hit) {
        result.push({ ...node })
        continue
      }
      const children = node.children === undefined ? [] : walk(node.children)
      if (children.length > 0) {
        result.push({ ...node, children })
      }
    }
    return result
  }
  return walk(menu)
}

/**
 * 扁平化菜单树（先序，含分组节点）。
 *
 * @param menu 菜单树。
 * @returns 扁平节点清单。
 */
export function flattenMenu(menu: readonly MenuNode[]): MenuNode[] {
  const result: MenuNode[] = []
  for (const node of menu) {
    result.push(node)
    if (node.children !== undefined) {
      result.push(...flattenMenu(node.children))
    }
  }
  return result
}

/**
 * 按路径查找菜单节点（先序，返回首个命中）。
 *
 * @param menu 菜单树。
 * @param path 路径。
 * @returns 命中的菜单节点；未命中返回 `undefined`。
 */
export function findMenuByPath(menu: readonly MenuNode[], path: string): MenuNode | undefined {
  for (const node of menu) {
    if (node.path === path) {
      return node
    }
    if (node.children !== undefined) {
      const found = findMenuByPath(node.children, path)
      if (found !== undefined) {
        return found
      }
    }
  }
  return undefined
}

/**
 * 菜单树转路由节点（供 `BaseDynamicRoutes.build`）。
 *
 * @param menu 菜单树。
 * @returns 路由节点树。
 */
export function toRouteNodes(menu: readonly MenuNode[]): RouteNode[] {
  return menu.map((node) => ({
    path: node.path,
    name: node.name ?? node.path,
    children: node.children === undefined ? undefined : toRouteNodes(node.children),
  }))
}

/** 占位菜单树：未接后端时驱动菜单完整交互（含多级 / 徽标 / 权限项）。 */
export const PLACEHOLDER_MENU: MenuNode[] = [
  { path: '/', title: '工作台', name: 'Home', icon: 'dashboard' },
  {
    path: '/system',
    title: '系统管理',
    icon: 'setting',
    children: [
      { path: '/system/user', title: '用户管理', name: 'SystemUser', permission: 'system:user:list' },
      { path: '/system/role', title: '角色管理', name: 'SystemRole', permission: 'system:role:list' },
      {
        path: '/system/dict',
        title: '字典管理',
        icon: 'notebook',
        children: [
          { path: '/system/dict/type', title: '字典类型', name: 'SystemDictType', permission: 'system:dict:list' },
          { path: '/system/dict/data', title: '字典数据', name: 'SystemDictData', permission: 'system:dict:data' },
        ],
      },
      { path: '/system/notice', title: '通知公告', name: 'SystemNotice', permission: 'system:notice:list', badge: 3 },
    ],
  },
  { path: '/audit', title: '审计日志', name: 'AuditLog', icon: 'document', permission: 'audit:log:list' },
]
