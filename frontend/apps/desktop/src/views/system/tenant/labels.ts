/** 租户管理页文案映射（仅配额维度；状态 / 模块状态已改由选项集快照提供）。 */

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
