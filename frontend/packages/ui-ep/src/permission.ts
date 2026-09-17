/**
 * ui-ep 权限判定注入点（宿主 / 应用装配注入）。
 *
 * 契约与判定语义单份在 `@bms/core`（`createPermissionGate`）：未设权限码（`null` /
 * `undefined` / 空）视为不限制；**未注入判定器时视为空集（无权限）**——占位期受控按钮按无权限保真。
 */

import { createPermissionGate, type PermissionChecker, type PermissionMode } from '@bms/core'

export type { PermissionChecker, PermissionMode } from '@bms/core'

const gate = createPermissionGate()

export function configurePermissionChecker(next: PermissionChecker | undefined): void {
  gate.configure(next)
}

export function checkPerm(code: string | string[] | null | undefined, mode: PermissionMode = 'any'): boolean {
  return gate.check(code, mode)
}
