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

/** 十进制位数判定结果。 */
export interface DecimalPlaces {
  /** 小数位数（去尾零后）。 */
  fraction: number
  /** 是否合法十进制。 */
  valid: boolean
}

/**
 * 取小数位数（**字符串判定，不经浮点**）。
 *
 * 用于精度校验：`Number.isInteger(value * 10 ** precision)` 会因浮点乘法误判
 * （如 `0.29 * 100 === 28.999999999999996`），故一律以文本位数判定。
 *
 * @param value 值。
 * @returns 小数位数与合法性。
 */
export function decimalPlaces(value: string | number): DecimalPlaces {
  const parsed = parse(value)
  if (parsed === undefined) {
    return { fraction: 0, valid: false }
  }
  return { fraction: parsed.fraction.replace(/0+$/, '').length, valid: true }
}

/**
 * 按 `precision` 位小数补齐（不足补零，**不四舍五入**；非法输入返回空串）。
 *
 * 与 `normalizeDecimal` 的差别：后者去尾零（值语义），本函数保留到指定位数（展示语义）。
 *
 * @param value 值。
 * @param precision 精度（0 ~ 6）。
 * @returns 补齐后的十进制文本。
 */
export function padDecimal(value: string | number, precision: number): string {
  const normalized = normalizeDecimal(value, precision)
  if (normalized === '') {
    return ''
  }
  const [integer, fraction = ''] = normalized.split('.')
  return fraction === '' && precision === 0 ? integer : `${integer}.${fraction.padEnd(precision, '0')}`
}

/**
 * 按十进制文本加千分位（**字符串分组，不经浮点**）。
 *
 * @param value 值（十进制字符串 / 数值）。
 * @param options 选项（精度与小数符号）。
 * @returns 千分位文本；非法输入返回空串。
 */
export function formatDecimal(value: string | number, options: { precision?: number } = {}): string {
  const parsed = parse(value)
  if (parsed === undefined) {
    return ''
  }
  const precision =
    options.precision === undefined ? parsed.fraction.replace(/0+$/, '').length : sanitizePrecision(options.precision)
  // 指定精度时按精度**补齐小数位**（金额展示口径：`1.5` 配 precision=2 → `1.50`）。
  const normalized =
    options.precision === undefined ? normalizeDecimal(value, precision) : padDecimal(value, precision)
  if (normalized === '') {
    return ''
  }
  const negative = normalized.startsWith('-')
  const unsigned = negative ? normalized.slice(1) : normalized
  const [integer, fraction] = unsigned.split('.')
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const body = fraction === undefined || fraction === '' ? grouped : `${grouped}.${fraction}`
  return negative ? `-${body}` : body
}

/** 中文大写数字（0 ~ 9）。 */
const CHINESE_DIGITS = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖'] as const

/** 中文大写整数节权位（个 / 万 / 亿）。 */
const CHINESE_SECTION_UNITS = ['', '万', '亿'] as const

/** 中文大写节内位权（个 / 拾 / 佰 / 仟）。 */
const CHINESE_POSITION_UNITS = ['', '拾', '佰', '仟'] as const

/**
 * 单个四位节转中文大写（节内去零、按位取权）。
 *
 * @param section 节数值文本（最多 4 位）。
 * @returns 中文大写文本。
 */
function sectionToChinese(section: string): string {
  let result = ''
  let pendingZero = false
  const digits = section.padStart(4, '0')
  for (let index = 0; index < digits.length; index += 1) {
    const digit = Number(digits[index])
    const position = digits.length - index - 1
    if (digit === 0) {
      pendingZero = result !== ''
      continue
    }
    if (pendingZero) {
      result += CHINESE_DIGITS[0]
      pendingZero = false
    }
    result += `${CHINESE_DIGITS[digit]}${CHINESE_POSITION_UNITS[position]}`
  }
  return result
}

/**
 * 整数文本转中文大写（节拆分 + 节权位 + 节间补零）。
 *
 * @param integer 整数位文本（不含符号，可含前导零）。
 * @returns 中文大写文本；`0` 返回「零」。
 */
function integerToChinese(integer: string): string {
  const trimmed = integer.replace(/^0+/, '')
  if (trimmed === '') {
    return CHINESE_DIGITS[0]
  }
  const sections: string[] = []
  for (let end = trimmed.length; end > 0; end -= 4) {
    sections.unshift(trimmed.slice(Math.max(0, end - 4), end))
  }
  let result = ''
  for (let index = 0; index < sections.length; index += 1) {
    const unit = CHINESE_SECTION_UNITS[sections.length - index - 1]
    const text = sectionToChinese(sections[index])
    if (text === '') {
      // 整节为零：仅在后续还有非零节时补一个「零」。
      if (result !== '' && sections.slice(index + 1).some((item) => Number(item) !== 0)) {
        result += CHINESE_DIGITS[0]
      }
      continue
    }
    // 节内不足四位（如「壹万零贰」）时补零。
    if (result !== '' && Number(sections[index]) < 1000) {
      result += CHINESE_DIGITS[0]
    }
    result += `${text}${unit}`
  }
  return result
}

/**
 * 金额转中文大写（合同 / 发票 / 凭证场景，纯函数）。
 *
 * 全程以十进制文本处理，不引入浮点；空值 / 非法输入返回空串。
 *
 * @param value 金额（十进制字符串 / 数值，元）。
 * @param options 选项（精度，缺省 2 位）。
 * @returns 中文大写金额（如「壹万贰仟叁佰肆拾伍元陆角柒分」）。
 */
export function toChineseUpper(value: string | number, options: { precision?: number } = {}): string {
  const parsed = parse(value)
  if (parsed === undefined) {
    return ''
  }
  const precision = options.precision === undefined ? 2 : sanitizePrecision(options.precision)
  const normalized = normalizeDecimal(value, precision)
  if (normalized === '') {
    return ''
  }
  const negative = normalized.startsWith('-')
  const unsigned = negative ? normalized.slice(1) : normalized
  const [integer, fraction = ''] = unsigned.split('.')

  // 角 / 分（精度不足两位时右侧补零）。
  const jiao = Number(fraction[0] ?? '0')
  const fen = Number(fraction[1] ?? '0')

  let text = `${integerToChinese(integer)}元`
  if (jiao === 0 && fen === 0) {
    text += '整'
  } else {
    if (jiao !== 0) {
      text += `${CHINESE_DIGITS[jiao]}角`
    } else if (fen !== 0) {
      text += CHINESE_DIGITS[0]
    }
    if (fen !== 0) {
      text += `${CHINESE_DIGITS[fen]}分`
    }
  }
  return negative ? `负${text}` : text
}
