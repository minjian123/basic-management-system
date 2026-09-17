/**
 * 侧边菜单数据工具（`MenuNode` / `SideMenu` / 菜单状态注入点共用）。
 *
 * 数据契约（`MenuItem`）在 `@bms/core`（框架无关）；本文件只保留 PC 菜单的纯工具函数。
 */

import type { MenuItem } from '@bms/core'

export type { MenuItem } from '@bms/core'

/** 菜单项唯一键（叶子取 path，父级取 name） */
export function menuKey(item: MenuItem): string {
  return item.path ?? item.name
}

/** 按关键字过滤菜单树（保留命中路径的父链；父命中保留其全部子） */
export function filterMenuTree(items: MenuItem[], keyword: string): MenuItem[] {
  const kw = keyword.trim().toLowerCase()
  if (!kw) {
    return items
  }
  const result: MenuItem[] = []
  for (const item of items) {
    const matchedSelf = item.name.toLowerCase().includes(kw)
    const matchedChildren = item.children ? filterMenuTree(item.children, kw) : []
    if (matchedSelf) {
      result.push(item)
    } else if (matchedChildren.length > 0) {
      result.push({ ...item, children: matchedChildren })
    }
  }
  return result
}

/** 找到目标 path 的祖先键链（展开用；返回不含目标自身） */
export function findAncestorKeys(
  items: MenuItem[],
  target: string,
  chain: string[] = [],
): string[] | null {
  for (const item of items) {
    if (item.path === target) {
      return chain
    }
    if (item.children) {
      const found = findAncestorKeys(item.children, target, [...chain, menuKey(item)])
      if (found) {
        return found
      }
    }
  }
  return null
}

/** 过滤（hidden）+ 排序（sort，递归） */
export function sortVisible(items: MenuItem[]): MenuItem[] {
  return [...items]
    .filter((item) => !item.hidden)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((item) => (item.children ? { ...item, children: sortVisible(item.children) } : item))
}
