/**
 * 数字域纯函数（框架无关核心）：数字框与金额 / 数值字段共用一套口径。
 *
 * 覆盖解析（中间态与非法输入）、精度归一、越界钳制、千分位格式化与反解析；
 * 双端（`ui-ep` / `ui-vant`）实现只做展示与事件桥接。
 */

export interface NumberParseOptions {
  /** 小数位（默认 0 = 整数） */
  precision?: number
  min?: number
  max?: number
  /** 越界钳制（默认 true）；false 时保留原值并以 `outOfRange` 供校验 */
  clamp?: boolean
}

export interface NumberParseResult {
  /** 归一后的数值（空 / 非法 → null） */
  value: number | null
  /** 输入是否曾越界（`clamp=false` 时供 `validate` 用） */
  outOfRange: boolean
  /** 是否含非法字符（已按合法前缀解析） */
  invalid: boolean
}

const THOUSANDS_SEPARATOR = ','
const NUMERIC_PREFIX = /^-?\d*\.?\d*/

/** 精度归一（四舍五入到 `precision` 位；`precision <= 0` 取整数） */
export function applyPrecision(value: number, precision = 0): number {
  const digits = precision < 0 ? 0 : Math.trunc(precision)
  if (digits === 0) {
    return Math.round(value)
  }
  const factor = 10 ** digits
  return Math.round(value * factor) / factor
}

/** 钳制到 `[min, max]`（缺省边界不限制） */
export function clampNumber(value: number, min?: number, max?: number): number {
  let next = value
  if (min !== undefined && next < min) {
    next = min
  }
  if (max !== undefined && next > max) {
    next = max
  }
  return next
}

/** 是否在范围内 */
export function inNumberRange(value: number, min?: number, max?: number): boolean {
  if (min !== undefined && value < min) {
    return false
  }
  if (max !== undefined && value > max) {
    return false
  }
  return true
}

/** 去千分位分隔符与空白（编辑聚焦用） */
export function parseFormattedNumber(text: string): string {
  return text.split(THOUSANDS_SEPARATOR).join('').replace(/\s/g, '')
}

/**
 * 解析输入文本 → 数值。
 *
 * 中间态（`''` / `-` / `.` / `-.`）返回 `null` 且 `invalid=false`；
 * 含非法字符时取合法前缀并置 `invalid=true`（值仍可用，由件层决定是否写入）。
 */
export function parseNumberInput(text: string, options: NumberParseOptions = {}): NumberParseResult {
  const raw = parseFormattedNumber(text)
  if (raw === '' || raw === '-' || raw === '.' || raw === '-.') {
    return { value: null, outOfRange: false, invalid: false }
  }

  const matched = NUMERIC_PREFIX.exec(raw)
  const candidate = matched ? matched[0] : ''
  if (candidate === '' || candidate === '-') {
    return { value: null, outOfRange: false, invalid: true }
  }

  const parsed = Number(candidate)
  if (!Number.isFinite(parsed)) {
    return { value: null, outOfRange: false, invalid: true }
  }

  const outOfRange = !inNumberRange(parsed, options.min, options.max)
  const normalized = options.clamp === false ? parsed : clampNumber(parsed, options.min, options.max)
  return {
    value: applyPrecision(normalized, options.precision ?? 0),
    outOfRange,
    invalid: candidate !== raw,
  }
}

/** 千分位格式化（仅显示层；`null` / `NaN` → `''`） */
export function formatNumber(
  value: number | null | undefined,
  options: { precision?: number; thousands?: boolean } = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return ''
  }
  const digits = Math.max(0, Math.trunc(options.precision ?? 0))
  const fixed = value.toFixed(digits)
  if (!options.thousands) {
    return fixed
  }
  const [intPart, decimalPart] = fixed.split('.')
  const sign = intPart.startsWith('-') ? '-' : ''
  const digitsOnly = sign === '' ? intPart : intPart.slice(1)
  const grouped = digitsOnly.replace(/\B(?=(\d{3})+(?!\d))/g, THOUSANDS_SEPARATOR)
  return decimalPart === undefined ? `${sign}${grouped}` : `${sign}${grouped}.${decimalPart}`
}
