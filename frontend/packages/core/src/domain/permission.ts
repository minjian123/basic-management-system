/**
 * 领域纯函数：权限判定（任一 / 全部 / 取反）——权限指令与脚本判定共用。
 */

/** 判定模式。 */
export type PermissionMode = 'any' | 'all' | 'not'

/**
 * 判定权限码集合是否满足要求。
 *
 * @param codes 已持有权限码。
 * @param required 要求权限码。
 * @param mode 判定模式（缺省 `any`）：`any` 任一满足 / `all` 全部满足 / `not` 全不满足。
 */
export function evaluatePermission(
  codes: Iterable<string>,
  required: readonly string[],
  mode: PermissionMode = 'any',
): boolean {
  const owned = new Set(codes)
  if (required.length === 0) {
    return mode !== 'any'
  }
  if (mode === 'all') {
    return required.every((code) => owned.has(code))
  }
  if (mode === 'not') {
    return required.every((code) => !owned.has(code))
  }
  return required.some((code) => owned.has(code))
}
