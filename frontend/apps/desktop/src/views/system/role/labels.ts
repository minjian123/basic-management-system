/**
 * 角色类型文案映射（契约 `role_type`：`custom` / `system` / `security` / `audit`）。
 *
 * 与后端 `bms_platform/models/role.py` 的 `ROLE_TYPES` 同源；前端只做展示映射，
 * **不做内置判定**（内置标记由后端 `builtin` 字段下发）。
 */

/** 角色类型 → 展示文案。 */
export const ROLE_TYPE_LABELS: Record<string, string> = {
  custom: '自定义',
  system: '系统管理员',
  security: '安全管理员',
  audit: '审计管理员',
}

/**
 * 取角色类型展示文案。
 *
 * @param roleType 契约角色类型（可能未定义或未知取值）。
 * @returns 展示文案；空值回退 `—`，未知取值原样回显。
 */
export function roleTypeLabel(roleType: string | undefined): string {
  if (!roleType) {
    return '—'
  }
  return ROLE_TYPE_LABELS[roleType] ?? roleType
}
