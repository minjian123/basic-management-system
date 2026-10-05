/**
 * 页签标题解析（《布局设计 · 主框架》§3.8）：优先取动态菜单名，回退路由 `meta.title`，最后回退路径。
 *
 * **不使用路由 `name`**——PascalCase 仅作代码标识，与展示标题解耦（菜单 i18n 变更无需发版）。
 */

import { findMenuByPath, type MenuNode } from '@bms/core'

/**
 * 解析页签标题。
 *
 * @param menu 当前菜单树（含模块菜单）。
 * @param metaTitle 路由 `meta.title`（可能为空 / 非字符串）。
 * @param path 路由路径（兜底标题）。
 * @returns 页签标题。
 */
export function resolveTabTitle(menu: readonly MenuNode[], metaTitle: unknown, path: string): string {
  const node = findMenuByPath(menu, path)
  if (node !== undefined) {
    return node.title
  }
  return typeof metaTitle === 'string' && metaTitle !== '' ? metaTitle : path
}
