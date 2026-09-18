/** 格式化工具（宿主层）：默认基准经配置注入，缺省走核心纯函数。 */

import {
  formatAmount as coreFormatAmount,
  formatDate as coreFormatDate,
  formatDateTime as coreFormatDateTime,
  formatDuration,
  formatFileSize,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  mask,
  type FormatContext,
} from '@bms/core'

/** 宿主格式化默认基准。 */
const defaults: Required<FormatContext> = { locale: 'zh-CN', timezone: 'Asia/Shanghai' }

/**
 * 配置宿主默认基准（用户时区 / locale 偏好注入）。
 *
 * @param context 基准。
 */
export function configureFormatDefaults(context: FormatContext): void {
  if (context.locale !== undefined) {
    defaults.locale = context.locale
  }
  if (context.timezone !== undefined) {
    defaults.timezone = context.timezone
  }
}

/** 合并默认基准。 */
function withDefaults(context: FormatContext = {}): FormatContext {
  return { locale: context.locale ?? defaults.locale, timezone: context.timezone ?? defaults.timezone }
}

/**
 * 格式化日期时间（宿主默认基准）。
 *
 * @param value 日期。
 * @param context 覆盖基准。
 */
export function formatDateTime(value: Parameters<typeof coreFormatDateTime>[0], context: FormatContext = {}): string {
  return coreFormatDateTime(value, withDefaults(context))
}

/**
 * 格式化日期（宿主默认基准）。
 *
 * @param value 日期。
 * @param context 覆盖基准。
 */
export function formatDate(value: Parameters<typeof coreFormatDate>[0], context: FormatContext = {}): string {
  return coreFormatDate(value, withDefaults(context))
}

/**
 * 格式化金额（宿主默认基准）。
 *
 * @param value 金额。
 * @param context 覆盖基准与货币 / 精度。
 */
export function formatAmount(
  value: number,
  context: FormatContext & { currency?: string; precision?: number } = {},
): string {
  return coreFormatAmount(value, { ...withDefaults(context), ...context })
}

export { formatDuration, formatFileSize, formatNumber, formatPercent, formatRelativeTime, mask }
