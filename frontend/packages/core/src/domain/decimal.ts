/**
 * 领域纯函数：十进制定点运算（金额 / 数值字段共用）。
 *
 * 全程以**字符串 / BigInt** 运算，不引入浮点；精度支持厘（3）/ 毫（4）等自定义小数位（0 ~ 6）。
 */

/** 精度上限。 */
export const MAX_DECIMAL_PRECISION = 6

/** 范围选项。 */
export interface DecimalRangeOptions {
  /** 下界（含）。 */
  min?: string | number
  /** 上界（含）。 */
  max?: string | number
  /** 精度（0 ~ 6）。 */
  precision?: number
}

/** 解析结果。 */
interface ParsedDecimal {
  /** 符号（负为 `true`）。 */
  negative: boolean
  /** 整数位。 */
  integer: string
  /** 小数位（原始，未归一）。 */
  fraction: string
}

/** 归一精度（非法取 0）。 */
export function sanitizePrecision(precision: number | undefined): number {
  if (precision === undefined || !Number.isFinite(precision)) {
    return 0
  }
  return Math.min(Math.max(Math.trunc(precision), 0), MAX_DECIMAL_PRECISION)
}

/**
 * 解析十进制文本为符号 / 整数位 / 小数位。
 *
 * @param value 值。
 * @returns 解析结果；非法返回 `undefined`。
 */
function parse(value: string | number): ParsedDecimal | undefined {
  const text = typeof value === 'number' ? String(value) : value.trim()
  if (text === '') {
    return undefined
  }
  const match = text.match(/^([+-]?)(\d*)(?:\.(\d*))?$/)
  if (match === null || (match[2] === '' && (match[3] === undefined || match[3] === ''))) {
    return undefined
  }
  return { negative: match[1] === '-', integer: match[2] === '' ? '0' : match[2], fraction: match[3] ?? '' }
}

/** 是否为合法十进制文本。 */
export function isDecimal(value: string | number): boolean {
  return parse(value) !== undefined
}

/**
 * 归一为 `precision` 位小数的十进制字符串（四舍五入，去尾零；非法输入返回空串）。
 *
 * @param value 值。
 * @param precision 精度（0 ~ 6）。
 */
export function normalizeDecimal(value: string | number, precision: number): string {
  const parsed = parse(value)
  if (parsed === undefined) {
    return ''
  }
  const size = sanitizePrecision(precision)
  const digits = parsed.fraction
  const kept = digits.slice(0, size).padEnd(size, '0')
  const roundDigit = digits.charAt(size)
  let minor = BigInt((parsed.integer + kept).replace(/^0+(?=\d)/, ''))
  if (roundDigit !== '' && Number(roundDigit) >= 5) {
    minor += 1n
  }
  const text = minor.toString().padStart(size + 1, '0')
  const integerPart = size === 0 ? text : text.slice(0, text.length - size)
  const fractionPart = size === 0 ? '' : text.slice(text.length - size).replace(/0+$/, '')
  const sign = parsed.negative && minor !== 0n ? '-' : ''
  return fractionPart === '' ? `${sign}${integerPart}` : `${sign}${integerPart}.${fractionPart}`
}

/**
 * 转最小单位（BigInt，字符串移位，无浮点）。
 *
 * @param value 值。
 * @param precision 精度（0 ~ 6）。
 */
export function toMinorUnits(value: string | number, precision: number): bigint {
  const parsed = parse(value)
  if (parsed === undefined) {
    return 0n
  }
  const size = sanitizePrecision(precision)
  const kept = parsed.fraction.slice(0, size).padEnd(size, '0')
  const units = BigInt((parsed.integer + kept).replace(/^0+(?=\d)/, '') || '0')
  return parsed.negative ? -units : units
}

/**
 * 由最小单位还原十进制字符串。
 *
 * @param units 最小单位。
 * @param precision 精度（0 ~ 6）。
 */
export function fromMinorUnits(units: bigint, precision: number): string {
  const size = sanitizePrecision(precision)
  const negative = units < 0n
  const text = (negative ? -units : units).toString().padStart(size + 1, '0')
  const integerPart = size === 0 ? text : text.slice(0, text.length - size)
  const fractionPart = size === 0 ? '' : text.slice(text.length - size)
  const body = size === 0 ? integerPart : `${integerPart}.${fractionPart}`
  return negative && units !== 0n ? `-${body}` : body
}

/**
 * 定点比较。
 *
 * @param a 左值。
 * @param b 右值。
 * @returns `-1` / `0` / `1`。
 */
export function compareDecimal(a: string | number, b: string | number): -1 | 0 | 1 {
  const left = toMinorUnits(a, MAX_DECIMAL_PRECISION)
  const right = toMinorUnits(b, MAX_DECIMAL_PRECISION)
  if (left < right) {
    return -1
  }
  return left > right ? 1 : 0
}

/**
 * 是否落在范围内（含端点；空值视为越界）。
 *
 * @param value 值。
 * @param options 范围与精度。
 */
export function isDecimalInRange(value: string | number, options: DecimalRangeOptions = {}): boolean {
  if (!isDecimal(value)) {
    return false
  }
  if (options.min !== undefined && compareDecimal(value, options.min) < 0) {
    return false
  }
  if (options.max !== undefined && compareDecimal(value, options.max) > 0) {
    return false
  }
  return true
}
