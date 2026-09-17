/**
 * 权限判定共享工厂（框架无关核心领域层）：判定器覆盖 / 恢复语义统一，判定器由宿主注入。
 *
 * 语义（与旧 `checkPerm` 一致）：未设权限码（`null` / `undefined` / 空串 / 空数组）视为不限制；
 * **未注入判定器时视为空集（无权限）**——占位期受控入口按无权限保真。
 */

import type { PermissionChecker, PermissionMode } from '../contracts/permission'

export interface PermissionGate {
  /** 注入判定器（传 `undefined` 恢复未注入语义） */
  configure(next: PermissionChecker | undefined): void
  /** 判定权限码（缺省 `any` 语义） */
  check(code: string | string[] | null | undefined, mode?: PermissionMode): boolean
}

export function createPermissionGate(): PermissionGate {
  let checker: PermissionChecker | undefined
  return {
    configure(next) {
      checker = next
    },
    check(code, mode = 'any') {
      if (code === null || code === undefined || code === '') {
        return true
      }
      const codes = Array.isArray(code) ? code : [code]
      if (codes.length === 0) {
        return true
      }
      if (!checker) {
        return false
      }
      return checker(codes, mode)
    },
  }
}
