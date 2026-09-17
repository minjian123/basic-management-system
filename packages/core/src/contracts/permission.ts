/** 权限判定契约（框架无关）：宿主注入的判定器接口面（动作权限与菜单过滤共用）。 */

export type PermissionMode = 'any' | 'all'

export type PermissionChecker = (codes: readonly string[], mode: PermissionMode) => boolean
