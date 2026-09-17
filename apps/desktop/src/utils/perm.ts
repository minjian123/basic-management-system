/**
 * 动作权限脚本判断：`hasPerm` / `canAccess`（不可指令化场景：表格列、工具栏、路由 meta）。
 *
 * 权限码集合与判定经 `@bms/ui-ep` 注入点（宿主装配 `configurePermissionChecker` 接权限 store）；
 * 前端显隐不构成安全边界，后端 `require_permission` 强校验为准。
 */

import { checkPerm } from '@bms/ui-ep'

/** `canAccess` 可判定目标：权限码或路由 / 菜单节点（`public` 或未声明 `permission` 视为公开） */
export interface AccessTarget {
  permission?: string | string[]
  public?: boolean
}

/** 编程式权限判断（`[]` 空数组视为不限制） */
export function hasPerm(code: string | string[], mode: 'any' | 'all' = 'any'): boolean {
  // 判定经 ui-ep 注入点（宿主装配接权限 store）
  return code === '' ? true : checkPerm(code, mode)
}

/** 访问判定：字符串 / 数组等价 `hasPerm`；节点对象取 `permission`；`null` / `undefined` 视为允许 */
export function canAccess(target: string | string[] | AccessTarget | null | undefined): boolean {
  if (target === null || target === undefined) {
    return true
  }
  if (typeof target === 'string' || Array.isArray(target)) {
    return hasPerm(target)
  }
  if (target.public === true || target.permission === undefined) {
    return true
  }
  return hasPerm(target.permission)
}
