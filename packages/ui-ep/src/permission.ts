/**
 * ui-ep 权限判定注入点（宿主 / 应用装配注入）。
 *
 * 语义与旧 `hasPerm` 一致：未设权限码（`null` / `undefined` / 空）视为不限制；
 * **未注入判定器时视为空集（无权限）**——占位期受控按钮按无权限保真。
 * 宿主在装配时注入（可接 `@bms/vue` 的权限能力 / 真实权限集合）。
 */

export type PermissionMode = 'any' | 'all'

export type PermissionChecker = (codes: readonly string[], mode: PermissionMode) => boolean

let checker: PermissionChecker | undefined

export function configurePermissionChecker(next: PermissionChecker | undefined): void {
  checker = next
}

export function checkPerm(code: string | string[] | null | undefined, mode: PermissionMode = 'any'): boolean {
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
}
