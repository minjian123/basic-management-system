/**
 * 通用格式化纯函数：日期时间 / 数值 / 金额 / 百分比 / 文件大小 / 时长 / 相对时间 / 脱敏。
 *
 * - 一律走 `Intl` API（按 `{locale, timezone, pattern/options}` 缓存实例复用）；
 * - 空值 / 非法值统一返回占位（缺省 `—`），不出现 `Invalid Date` / `NaN`；
 * - 默认 locale / 时区经 `configureFormatDefaults` 注入（缺省 i18n locale + 浏览器时区）；
 * - 金额只格式化不参与运算（后端以字符串 / 定点传输）。
 */

import { i18n } from '@/i18n'

/** 格式化默认基准（locale / timezone） */
export interface FormatDefaults {
  locale: string
  timezone: string
}

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

function currentLocale(): string {
  const locale = i18n.global.locale
  return typeof locale === 'string' ? locale : locale.value
}

let defaults: FormatDefaults = { locale: currentLocale(), timezone: browserTimezone() }

/** 注入格式化默认基准（入口 / `useTimezone`；单函数调用仍可显式覆盖） */
export function configureFormatDefaults(patch: Partial<FormatDefaults>): void {
  defaults = { ...defaults, ...patch }
}

/** 取当前默认基准（快照） */
export function getFormatDefaults(): FormatDefaults {
  return { ...defaults }
}

/** 复位默认基准（测试用） */
export function resetFormatDefaults(): void {
  defaults = { locale: currentLocale(), timezone: browserTimezone() }
}

/** 通用格式化选项 */
export interface FormatOptions {
  locale?: string
  timezone?: string
  placeholder?: string
}

const DEFAULT_PLACEHOLDER = '—'

function placeholderOf(options: FormatOptions = {}): string {
  return options.placeholder ?? DEFAULT_PLACEHOLDER
}

function toDate(value: unknown): Date | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  const date = value instanceof Date ? value : new Date(value as string | number)
  return Number.isNaN(date.getTime()) ? undefined : date
}

function toNumber(value: unknown): number | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!/^-?\d+(\.\d+)?$/.test(trimmed)) {
      return undefined
    }
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : undefined
  }
  return undefined
}

function t(key: string, fallback: string, locale?: string): string {
  const target = locale ?? currentLocale()
  const messages = i18n.global.getLocaleMessage(target) as Record<string, unknown>
  const text = key.split('.').reduce<unknown>((acc, part) => {
    if (acc && typeof acc === 'object') {
      return (acc as Record<string, unknown>)[part]
    }
    return undefined
  }, messages)
  return typeof text === 'string' ? text : fallback
}

// ---- Intl 实例缓存 ----

const dateTimeFormats = new Map<string, Intl.DateTimeFormat>()
const numberFormats = new Map<string, Intl.NumberFormat>()
const relativeFormats = new Map<string, Intl.RelativeTimeFormat>()

function dateTimeFormatter(locale: string, timezone: string): Intl.DateTimeFormat {
  const key = `${locale}|${timezone}`
  let formatter = dateTimeFormats.get(key)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    })
    dateTimeFormats.set(key, formatter)
  }
  return formatter
}

function numberFormatter(locale: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${locale}|${JSON.stringify(options)}`
  let formatter = numberFormats.get(key)
  if (!formatter) {
    formatter = new Intl.NumberFormat(locale, options)
    numberFormats.set(key, formatter)
  }
  return formatter
}

function relativeFormatter(locale: string): Intl.RelativeTimeFormat {
  let formatter = relativeFormats.get(locale)
  if (!formatter) {
    formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'always' })
    relativeFormats.set(locale, formatter)
  }
  return formatter
}

/** 按 token 组装（yyyy / MM / dd / HH / mm / ss） */
function applyPattern(parts: Record<string, string>, pattern: string): string {
  return pattern.replace(/yyyy|MM|dd|HH|mm|ss/g, (token) => parts[token] ?? token)
}

function timeParts(date: Date, locale: string, timezone: string): Record<string, string> {
  const parts = dateTimeFormatter(locale, timezone).formatToParts(date)
  const found: Record<string, string> = {}
  for (const part of parts) {
    found[part.type] = part.value
  }
  return {
    yyyy: found['year'] ?? '',
    MM: found['month'] ?? '',
    dd: found['day'] ?? '',
    HH: found['hour'] ?? '',
    mm: found['minute'] ?? '',
    ss: found['second'] ?? '',
  }
}

// ---- 日期时间 ----

export function formatDateTime(
  value: unknown,
  options: FormatOptions & { pattern?: string; seconds?: boolean } = {},
): string {
  const date = toDate(value)
  if (!date) {
    return placeholderOf(options)
  }
  const pattern = options.pattern ?? (options.seconds === true ? 'yyyy-MM-dd HH:mm:ss' : 'yyyy-MM-dd HH:mm')
  const parts = timeParts(date, options.locale ?? defaults.locale, options.timezone ?? defaults.timezone)
  return applyPattern(parts, pattern)
}

export function formatDate(value: unknown, options: FormatOptions & { pattern?: string } = {}): string {
  return formatDateTime(value, { ...options, pattern: options.pattern ?? 'yyyy-MM-dd' })
}

export function formatDateRange(value: [unknown, unknown] | null | undefined, options: FormatOptions = {}): string {
  if (!value || value.length < 2) {
    return placeholderOf(options)
  }
  return `${formatDate(value[0], options)} ~ ${formatDate(value[1], options)}`
}

function dateKeyOf(date: Date, locale: string, timezone: string): string {
  const parts = timeParts(date, locale, timezone)
  return `${parts['yyyy'] ?? ''}-${parts['MM'] ?? ''}-${parts['dd'] ?? ''}`
}

export function formatRelativeTime(value: unknown, options: FormatOptions & { now?: Date } = {}): string {
  const date = toDate(value)
  if (!date) {
    return placeholderOf(options)
  }
  const locale = options.locale ?? defaults.locale
  const timezone = options.timezone ?? defaults.timezone
  const now = options.now ?? new Date()
  const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  if (diffSeconds >= 0 && diffSeconds < 60) {
    return t('common.justNow', '刚刚', locale)
  }
  if (diffSeconds >= 60 && diffSeconds < 3600) {
    return relativeFormatter(locale).format(-Math.floor(diffSeconds / 60), 'minute')
  }
  if (diffSeconds >= 3600 && diffSeconds < 86400) {
    return relativeFormatter(locale).format(-Math.floor(diffSeconds / 3600), 'hour')
  }
  const yesterday = new Date(now.getTime() - 86400_000)
  if (dateKeyOf(date, locale, timezone) === dateKeyOf(yesterday, locale, timezone)) {
    return `${t('common.yesterday', '昨天', locale)} ${formatDateTime(date, { ...options, pattern: 'HH:mm' })}`
  }
  return formatDate(date, options)
}

// ---- 数值 / 金额 / 百分比 ----

export function formatNumber(
  value: unknown,
  options: FormatOptions & { precision?: number; grouping?: boolean } = {},
): string {
  const number = toNumber(value)
  if (number === undefined) {
    return placeholderOf(options)
  }
  const formatter = numberFormatter(options.locale ?? defaults.locale, {
    useGrouping: options.grouping !== false,
    ...(options.precision !== undefined
      ? { minimumFractionDigits: options.precision, maximumFractionDigits: options.precision }
      : {}),
  })
  return formatter.format(number)
}

export function formatAmount(
  value: unknown,
  options: FormatOptions & { precision?: number; currency?: string; symbol?: boolean } = {},
): string {
  const number = toNumber(value)
  if (number === undefined) {
    return placeholderOf(options)
  }
  const precision = options.precision ?? 2
  const formatter = numberFormatter(options.locale ?? defaults.locale, {
    ...(options.currency
      ? { style: 'currency', currency: options.currency }
      : options.symbol === false
        ? {}
        : { style: 'currency', currency: 'CNY' }),
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  })
  return formatter.format(number)
}

export function formatPercent(
  value: unknown,
  options: FormatOptions & { precision?: number; ratio?: boolean } = {},
): string {
  const number = toNumber(value)
  if (number === undefined) {
    return placeholderOf(options)
  }
  const precision = options.precision ?? 2
  if (options.ratio === true) {
    return numberFormatter(options.locale ?? defaults.locale, {
      style: 'percent',
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    }).format(number)
  }
  return `${formatNumber(number, { ...options, precision })}%`
}

// ---- 文件大小 / 时长 ----

const FILE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

export function formatFileSize(bytes: unknown, options: FormatOptions & { precision?: number } = {}): string {
  const size = toNumber(bytes)
  if (size === undefined || size < 0) {
    return placeholderOf(options)
  }
  const precision = options.precision ?? 2
  let value = size
  let unitIndex = 0
  while (value >= 1024 && unitIndex < FILE_UNITS.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  const unit = FILE_UNITS[unitIndex] ?? 'B'
  const text = unitIndex === 0 ? String(Math.round(value)) : value.toFixed(precision).replace(/\.?0+$/, '')
  return `${text} ${unit}`
}

export function formatDuration(seconds: unknown, options: FormatOptions = {}): string {
  const total = toNumber(seconds)
  if (total === undefined || total < 0) {
    return placeholderOf(options)
  }
  const locale = options.locale ?? defaults.locale
  const rounded = Math.floor(total)
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const secs = rounded % 60
  if (rounded === 0) {
    return `0 ${t('common.second', '秒', locale)}`
  }
  const parts: string[] = []
  if (hours > 0) {
    parts.push(`${hours} ${t('common.hour', '小时', locale)}`)
  }
  if (minutes > 0) {
    parts.push(`${minutes} ${t('common.minute', '分', locale)}`)
  }
  if (secs > 0) {
    parts.push(`${secs} ${t('common.second', '秒', locale)}`)
  }
  return parts.join(' ')
}

// ---- 脱敏 ----

export type MaskType = 'phone' | 'email' | 'idcard' | 'generic'

export function maskValue(value: unknown, type: MaskType = 'generic'): string {
  const text = value === undefined || value === null ? '' : String(value)
  if (text.length === 0) {
    return DEFAULT_PLACEHOLDER
  }
  if (type === 'phone') {
    const match = /^(\d{3})\d{4}(\d{4})$/.exec(text)
    return match ? `${match[1]}****${match[2]}` : maskGeneric(text)
  }
  if (type === 'email') {
    const match = /^([^@]+)@(.+)$/.exec(text)
    return match ? `${match[1]?.slice(0, 1)}***@${match[2]}` : maskGeneric(text)
  }
  if (type === 'idcard') {
    if (text.length < 6) {
      return maskGeneric(text)
    }
    return `${text.slice(0, 4)}${'*'.repeat(text.length - 6)}${text.slice(-2)}`
  }
  return maskGeneric(text)
}

function maskGeneric(text: string): string {
  if (text.length <= 2) {
    return '*'.repeat(text.length)
  }
  return `${text.slice(0, 1)}${'*'.repeat(text.length - 2)}${text.slice(-1)}`
}
