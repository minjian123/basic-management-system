/** 租户管理页文案映射（状态 / 模块状态 / 配额维度）。 */

/** 租户状态筛选项。 */
export const TENANT_STATUS_OPTIONS: ReadonlyArray<{ label: string; value: string }> = [
  { label: '开通中', value: 'provisioning' },
  { label: '启用', value: 'active' },
  { label: '停用', value: 'suspended' },
]

/**
 * 租户状态文案。
 *
 * @param status 状态取值。
 */
export function tenantStatusLabel(status: string | undefined): string {
  if (status === 'provisioning') {
    return '开通中'
  }
  if (status === 'suspended') {
    return '停用'
  }
  return '启用'
}

/**
 * 租户状态标签类型（Element Plus `el-tag` 的 `type`）。
 *
 * @param status 状态取值。
 */
export function tenantStatusTag(status: string | undefined): 'success' | 'warning' | 'info' {
  if (status === 'provisioning') {
    return 'warning'
  }
  if (status === 'suspended') {
    return 'info'
  }
  return 'success'
}

/** 模块状态筛选项（详情页三态展示用）。 */
export const MODULE_STATUS_OPTIONS: ReadonlyArray<{ label: string; value: string }> = [
  { label: '已启用', value: 'enabled' },
  { label: '已停用', value: 'disabled' },
  { label: '未开通', value: 'not_opened' },
]

/**
 * 模块状态文案。
 *
 * @param status 模块状态。
 */
export function moduleStatusLabel(status: string | undefined): string {
  if (status === 'disabled') {
    return '已停用'
  }
  if (status === 'enabled') {
    return '已启用'
  }
  return '未开通'
}

/** 配额维度文案。 */
const QUOTA_LABELS: Readonly<Record<string, string>> = {
  user_count: '用户数',
  storage_bytes: '存储空间',
  open_calls: '开放接口调用量',
}

/**
 * 配额维度文案。
 *
 * @param key 配额维度。
 */
export function quotaLabel(key: string): string {
  return QUOTA_LABELS[key] ?? key
}

/**
 * 配额维度单位。
 *
 * @param key 配额维度。
 */
export function quotaUnit(key: string): string {
  if (key === 'storage_bytes') {
    return '字节'
  }
  if (key === 'open_calls') {
    return '次'
  }
  return '个'
}
