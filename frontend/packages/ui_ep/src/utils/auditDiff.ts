/** 审计差异值渲染纯函数：类型推断 / 类型感知格式化 / 变更类型判定（复用核心格式化函数）。 */

import { EMPTY_PLACEHOLDER, formatAmount, formatDateTime, formatNumber, type FormatContext } from '@bms/core'

/** 审计值渲染类型。 */
export type AuditValueType = 'text' | 'number' | 'amount' | 'date' | 'boolean' | 'json' | 'richtext' | 'dict'

/** 变更类型。 */
export type AuditDiffKind = 'added' | 'removed' | 'modified' | 'unchanged'

/** 是否空值。 */
function isBlank(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

/** 判断字符串是否为日期时间形态。 */
function looksLikeDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?/.test(value)
}

/**
 * 推断值的渲染类型。
 *
 * @param value 值。
 */
export function inferValueType(value: unknown): AuditValueType {
  if (value === undefined || value === null) {
    return 'text'
  }
  if (typeof value === 'boolean') {
    return 'boolean'
  }
  if (typeof value === 'number') {
    return 'number'
  }
  if (typeof value === 'object') {
    return 'json'
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      return 'json'
    }
    if (looksLikeDate(trimmed)) {
      return 'date'
    }
  }
  return 'text'
}

/** 去除富文本标签，取纯文本摘要。 */
function stripTags(value: string): string {
  return value.replace(/<[^>]*>/g, '')
}

/**
 * 按类型格式化差异值（脱敏值 `***` 原样返回）。
 *
 * @param value 值。
 * @param type 渲染类型（缺省按值推断）。
 * @param context 格式化上下文。
 */
export function formatDiffValue(
  value: unknown,
  type?: AuditValueType,
  context: FormatContext = {},
): string {
  if (isBlank(value)) {
    return EMPTY_PLACEHOLDER
  }
  const resolved = type ?? inferValueType(value)
  switch (resolved) {
    case 'number':
      return typeof value === 'number' ? formatNumber(value, context) : String(value)
    case 'amount':
      return typeof value === 'number' ? formatAmount(value, context) : String(value)
    case 'boolean':
      return value === true || value === 'true' ? '是' : '否'
    case 'date':
      return formatDateTime(value as string, context)
    case 'json': {
      if (typeof value === 'string') {
        try {
          return JSON.stringify(JSON.parse(value), null, 2)
        } catch {
          return value
        }
      }
      try {
        return JSON.stringify(value, null, 2)
      } catch {
        return String(value)
      }
    }
    case 'richtext':
      return stripTags(String(value))
    case 'dict':
    case 'text':
    default:
      return String(value)
  }
}

/**
 * 判定变更类型。
 *
 * @param oldValue 旧值。
 * @param newValue 新值。
 */
export function diffKind(oldValue: unknown, newValue: unknown): AuditDiffKind {
  const oldBlank = isBlank(oldValue)
  const newBlank = isBlank(newValue)
  if (oldBlank && newBlank) {
    return 'unchanged'
  }
  if (oldBlank) {
    return 'added'
  }
  if (newBlank) {
    return 'removed'
  }
  return Object.is(oldValue, newValue) ? 'unchanged' : 'modified'
}
