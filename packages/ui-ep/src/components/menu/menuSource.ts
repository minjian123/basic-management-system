/**
 * 菜单状态注入点（非受控模式）：展开集与清除/展开动作由宿主注入。
 *
 * 契约与覆盖 / 恢复语义单份在 `@bms/core`（`createMenuSourceService`）；非受控模式
 * （`SideMenu` 的 `menus` 为 `null`）读取注入的可见菜单与展开集；**未注入 = 空菜单**
 * （占位保真，对齐旧 store「未注入 loader 置空清单」语义）；展开集持久化归宿主（`03_05` 口径）。
 */

import { createMenuSourceService, type MenuSourceProvider } from '@bms/core'

export type { MenuItem, MenuSourceProvider } from '@bms/core'

const service = createMenuSourceService()

/** 注入菜单状态提供者（传 `undefined` 恢复未注入） */
export function configureMenuSource(next: MenuSourceProvider | undefined): void {
  service.configure(next)
}

/** 读取菜单状态提供者（未注入返回 `undefined`） */
export function getMenuSource(): MenuSourceProvider | undefined {
  return service.get()
}
