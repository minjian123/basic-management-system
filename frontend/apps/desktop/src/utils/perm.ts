/** 权限判定（脚本场景）：权限码集合唯一来源，判定经核心纯函数。 */

import { evaluatePermission, type PermissionMode } from '@bms/core'

const codes = new Set<string>()

/**
 * 设置当前权限码集合（登录 / 权限刷新时调用）。
 *
 * @param next 权限码。
 */
export function setPermissionCodes(next: Iterable<string>): void {
  codes.clear()
  for (const code of next) {
    codes.add(code)
  }
}

/** 读取当前权限码集合。 */
export function getPermissionCodes(): string[] {
  return [...codes]
}

/**
 * 是否具备权限（默认任一满足）。
 *
 * @param required 要求权限码（单个或数组）。
 * @param mode 判定模式。
 */
export function hasPerm(required: string | readonly string[], mode: PermissionMode = 'any'): boolean {
  const list = typeof required === 'string' ? [required] : required
  return evaluatePermission(codes, list, mode)
}

/** 是否可访问（`hasPerm` 别名）。 */
export const canAccess = hasPerm
