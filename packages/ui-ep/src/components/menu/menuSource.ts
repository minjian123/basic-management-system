/**
 * 菜单状态注入点（非受控模式）：展开集与清除/展开动作由宿主注入。
 *
 * - 受控模式（`SideMenu` 传 `menus` 数组）不消费本注入点，完全 props 驱动；
 * - 非受控模式（`menus` 为 `null`）读取注入的可见菜单与展开集；**未注入 = 空菜单**
 *   （占位保真，对齐旧 store「未注入 loader 置空清单」语义）；
 * - 展开集持久化归宿主（`03_05` 口径）。
 */

import type { MenuItem } from './types'

export interface MenuSourceProvider {
  /** 可见菜单树（已过滤 hidden / 排序） */
  visibleMenus: () => MenuItem[]
  /** 展开集（非受控初始展开） */
  expandedKeys: () => string[]
  /** 记录某键展开态变更 */
  setExpanded: (key: string, open: boolean) => void
  /** 展开目标 path 的祖先链 */
  expandByPath: (path: string) => void
}

let provider: MenuSourceProvider | undefined

/** 注入菜单状态提供者（传 `undefined` 恢复未注入） */
export function configureMenuSource(next: MenuSourceProvider | undefined): void {
  provider = next
}

/** 读取菜单状态提供者（未注入返回 `undefined`） */
export function getMenuSource(): MenuSourceProvider | undefined {
  return provider
}
