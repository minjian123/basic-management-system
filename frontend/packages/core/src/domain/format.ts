/**
 * 领域纯函数：格式化（时间 / 数值 / 金额 / 文件大小 / 时长 / 相对时间 / 脱敏）。
 *
 * 一律走 `Intl`；空值与非法值返回占位 `—`；缺省 locale `zh-CN`、时区 `Asia/Shanghai`。
 */

/** 格式化上下文。 */
export interface FormatContext {
  /** 语言（缺省 `zh-CN`）。 */
  locale?: string
  /** 时区（缺省 `Asia/Shanghai`）。 */
  timezone?: string
}

/** 空值 / 非法值占位。 */
export const EMPTY_PLACEHOLDER = '—'

/** 缺省语言。 */
const DEFAULT_LOCALE = 'zh-CN'
/** 缺省时区。 */
const DEFAULT_TIMEZONE = 'Asia/Shanghai'

/** 归一为 `Date`（非法返回 `undefined`）。 */
function toDate(value: Date | string | number): Date | undefined {
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date
}

/**
 * 格式化日期时间。
 *
 * @param value 日期。
 * @param context 格式化上下文。
 */
export function formatDateTime(value: Date | string | number, context: FormatContext = {}): string {
  const date = toDate(value)
  if (date === undefined) {
    return EMPTY_PLACEHOLDER
  }
  return new Intl.DateTimeFormat(context.locale ?? DEFAULT_LOCALE, {
    timeZone: context.timezone ?? DEFAULT_TIMEZONE,
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(date)
}

/**
 * 格式化日期。
 *
 * @param value 日期。
 * @param context 格式化上下文。
 */
export function formatDate(value: Date | string | number, context: FormatContext = {}): string {
  const date = toDate(value)
  if (date === undefined) {
    return EMPTY_PLACEHOLDER
  }
  return new Intl.DateTimeFormat(context.locale ?? DEFAULT_LOCALE, {
    timeZone: context.timezone ?? DEFAULT_TIMEZONE,
    dateStyle: 'medium',
  }).format(date)
}

/**
 * 格式化金额（只格式化不运算）。
 *
 * @param value 金额。
 * @param context 格式化上下文与货币 / 精度。
 */
export function formatAmount(
  value: number,
  context: FormatContext & { currency?: string; precision?: number } = {},
): string {
  if (!Number.isFinite(value)) {
    return EMPTY_PLACEHOLDER
  }
  const precision = context.precision ?? 2
  return new Intl.NumberFormat(context.locale ?? DEFAULT_LOCALE, {
    style: 'currency',
    currency: context.currency ?? 'CNY',
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(value)
}

/**
 * 格式化数值（千分位）。
 *
 * @param value 数值。
 * @param context 格式化上下文。
 */
export function formatNumber(value: number, context: FormatContext = {}): string {
  if (!Number.isFinite(value)) {
    return EMPTY_PLACEHOLDER
  }
  return new Intl.NumberFormat(context.locale ?? DEFAULT_LOCALE).format(value)
}

/**
 * 格式化百分比（`value` 为小数，如 `0.12` → `12%`）。
 *
 * @param value 小数。
 * @param context 格式化上下文与精度。
 */
export function formatPercent(value: number, context: FormatContext & { precision?: number } = {}): string {
  if (!Number.isFinite(value)) {
    return EMPTY_PLACEHOLDER
  }
  const precision = context.precision ?? 2
  return new Intl.NumberFormat(context.locale ?? DEFAULT_LOCALE, {
    style: 'percent',
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }).format(value)
}

/**
 * 格式化文件大小。
 *
 * @param bytes 字节数。
 */
export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) {
    return EMPTY_PLACEHOLDER
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${unit === 0 ? value : value.toFixed(2)} ${units[unit]}`
}

/**
 * 格式化时长（毫秒 → `1h 2m 3s`）。
 *
 * @param ms 毫秒。
 */
export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) {
    return EMPTY_PLACEHOLDER
  }
  const totalSeconds = Math.floor(ms / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return [hours > 0 ? `${hours}h` : '', minutes > 0 ? `${minutes}m` : '', `${seconds}s`]
    .filter((part) => part !== '')
    .join(' ')
}

/**
 * 格式化相对时间（如「3 天前」）。
 *
 * @param value 时间。
 * @param context 格式化上下文与基准时间。
 */
export function formatRelativeTime(
  value: Date | string | number,
  context: FormatContext & { base?: Date } = {},
): string {
  const date = toDate(value)
  if (date === undefined) {
    return EMPTY_PLACEHOLDER
  }
  const base = context.base ?? new Date()
  const diffSeconds = Math.round((date.getTime() - base.getTime()) / 1000)
  const formatter = new Intl.RelativeTimeFormat(context.locale ?? DEFAULT_LOCALE, { numeric: 'auto' })
  const thresholds: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['year', 365 * 24 * 3600],
    ['month', 30 * 24 * 3600],
    ['day', 24 * 3600],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, seconds] of thresholds) {
    if (Math.abs(diffSeconds) >= seconds) {
      return formatter.format(Math.round(diffSeconds / seconds), unit)
    }
  }
  return formatter.format(diffSeconds, 'second')
}

/**
 * 脱敏（保留首尾，中间以 `*` 替换）。
 *
 * @param value 原值。
 * @param options 保留首尾长度。
 */
export function mask(value: string, options: { head?: number; tail?: number } = {}): string {
  const head = options.head ?? 3
  const tail = options.tail ?? 4
  if (value.length <= head + tail) {
    return '*'.repeat(value.length)
  }
  return `${value.slice(0, head)}${'*'.repeat(value.length - head - tail)}${value.slice(value.length - tail)}`
}

/**
 * 紧凑时间戳（`yyyyMMddHHmmss`，本地时区；下载文件名用）。
 *
 * @param value 日期（缺省当前时间）。
 * @returns 14 位紧凑时间戳；非法值回落空串。
 */
export function formatCompactTimestamp(value: Date | number = new Date()): string {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  const pad = (input: number): string => String(input).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}
