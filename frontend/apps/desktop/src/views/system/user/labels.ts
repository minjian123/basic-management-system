/** 用户管理 / 账号锁定页文案映射（状态、锁定类型、解锁方式）。 */

/** 用户状态取值。 */
export type UserStatusValue = 'enabled' | 'disabled'

/** 用户状态下拉选项。 */
export const USER_STATUS_OPTIONS: ReadonlyArray<{ label: string; value: UserStatusValue }> = [
  { label: '启用', value: 'enabled' },
  { label: '停用', value: 'disabled' },
]

/**
 * 用户状态文案。
 *
 * @param status 状态取值。
 */
export function userStatusLabel(status: string | undefined): string {
  return status === 'disabled' ? '停用' : '启用'
}

/** 锁定类型文案映射。 */
const LOCK_TYPE_LABELS: Readonly<Record<string, string>> = {
  fail_limit: '登录失败超限',
  inactive: '长期未登录',
  manual: '手动锁定',
}

/** 锁定类型标签类型映射。 */
const LOCK_TYPE_TAGS: Readonly<Record<string, 'warning' | 'danger' | 'info'>> = {
  fail_limit: 'warning',
  inactive: 'danger',
  manual: 'info',
}

/** 锁定类型筛选项。 */
export const LOCK_TYPE_OPTIONS: ReadonlyArray<{ label: string; value: string }> = [
  { label: '登录失败超限', value: 'fail_limit' },
  { label: '长期未登录', value: 'inactive' },
  { label: '手动锁定', value: 'manual' },
]

/** 解锁状态筛选项（`open` → `active=true`；`done` → `active=false`，含已到期自动解锁的记录）。 */
export const UNLOCK_STATE_OPTIONS: ReadonlyArray<{ label: string; value: string }> = [
  { label: '未解锁', value: 'open' },
  { label: '已解锁（含已到期）', value: 'done' },
]

/**
 * 锁定类型文案。
 *
 * @param lockType 锁定类型取值。
 */
export function lockTypeLabel(lockType: string): string {
  return LOCK_TYPE_LABELS[lockType] ?? lockType
}

/**
 * 锁定类型标签类型（Element Plus `el-tag` 的 `type`）。
 *
 * @param lockType 锁定类型取值。
 */
export function lockTypeTag(lockType: string): 'warning' | 'danger' | 'info' {
  return LOCK_TYPE_TAGS[lockType] ?? 'info'
}

/**
 * 时间展示（UTC ISO → `YYYY-MM-DD HH:mm:ss`；空值显示 `—`）。
 *
 * @param value ISO 时间字符串或空值。
 */
export function formatDateTime(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return '—'
  }
  return value.replace('T', ' ').slice(0, 19)
}

/**
 * 解锁方式文案。
 *
 * @param mode 解锁方式（`manual` / `auto`；未解锁为 `null`）。
 */
export function unlockModeLabel(mode: string | null | undefined): string {
  if (mode === 'manual') {
    return '手动解锁'
  }
  if (mode === 'auto') {
    return '自动解锁'
  }
  return '—'
}
