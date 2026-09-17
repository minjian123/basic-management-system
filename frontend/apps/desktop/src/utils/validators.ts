/** 常用校验 predicates 与规则工厂（框架无关：Element Plus / Vant 规则可直接使用）。 */

const PHONE_RE = /^1[3-9]\d{9}$/
const EMAIL_RE = /^[\w.+-]+@[\w-]+(\.[\w-]+)+$/
const ID_CARD_RE = /^\d{17}[\dXx]$/
const URL_RE = /^https?:\/\/[^\s]+$/

export function isPhone(value: string): boolean {
  return PHONE_RE.test(value)
}

export function isEmail(value: string): boolean {
  return EMAIL_RE.test(value)
}

export function isIdCard(value: string): boolean {
  return ID_CARD_RE.test(value)
}

export function isUrl(value: string): boolean {
  return URL_RE.test(value)
}

export type PasswordStrength = 'weak' | 'medium' | 'strong'

export function passwordStrength(value: string): PasswordStrength {
  let classes = 0
  if (/[a-z]/.test(value)) classes += 1
  if (/[A-Z]/.test(value)) classes += 1
  if (/\d/.test(value)) classes += 1
  if (/[^A-Za-z0-9]/.test(value)) classes += 1
  if (value.length >= 12 && classes >= 3) {
    return 'strong'
  }
  if (value.length >= 8 && classes >= 2) {
    return 'medium'
  }
  return 'weak'
}

export interface FieldRule {
  required?: boolean
  pattern?: RegExp
  validator?: (rule: unknown, value: unknown, callback: (error?: Error) => void) => void
  message: string
  trigger: 'blur' | 'change'
}

export function required(message = '必填项'): FieldRule {
  return { required: true, message, trigger: 'blur' }
}

export function pattern(regExp: RegExp, message: string): FieldRule {
  return { pattern: regExp, message, trigger: 'blur' }
}

/** 空值判定（空值跳过校验，必填由 `required` 负责） */
function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

/** 通过校验（不回调错误） */
function pass(callback: (error?: Error) => void): void {
  callback()
}

/** 失败校验（回调错误） */
function fail(message: string, callback: (error?: Error) => void): void {
  callback(new Error(message))
}

/** 长度区间（空值跳过） */
export function lengthRange(min: number, max: number, message?: string): FieldRule {
  const text = message ?? `长度需在 ${min} ~ ${max} 之间`
  return {
    message: text,
    trigger: 'blur',
    validator: (_rule, value, callback) => {
      if (isEmpty(value)) {
        pass(callback)
        return
      }
      const length = String(value).length
      if (length < min || length > max) {
        fail(text, callback)
        return
      }
      pass(callback)
    },
  }
}

/** 正则规则（`pattern` 供 el-form / Vant 原生消费，`validator` 供框架无关消费） */
function regexRule(regExp: RegExp, message: string, trigger: 'blur' | 'change' = 'blur'): FieldRule {
  return {
    pattern: regExp,
    message,
    trigger,
    validator: (_rule, value, callback) => {
      if (isEmpty(value)) {
        pass(callback)
        return
      }
      if (regExp.test(String(value))) {
        pass(callback)
        return
      }
      fail(message, callback)
    },
  }
}

/** 邮箱格式 */
export function email(message = '邮箱格式不正确'): FieldRule {
  return regexRule(EMAIL_RE, message)
}

/** 手机号格式 */
export function phone(message = '手机号格式不正确'): FieldRule {
  return regexRule(PHONE_RE, message)
}

/** URL 格式 */
export function url(message = '链接格式不正确'): FieldRule {
  return regexRule(URL_RE, message)
}

/** 金额：精度（小数位 ≤ precision）与区间（空值跳过） */
export function amount(options: { min?: number; max?: number; precision?: number } = {}, message?: string): FieldRule {
  const text = message ?? '金额格式不正确'
  return {
    message: text,
    trigger: 'blur',
    validator: (_rule, value, callback) => {
      if (isEmpty(value)) {
        pass(callback)
        return
      }
      const raw = String(value).trim()
      const precision = options.precision ?? 2
      const decimal = raw.includes('.') ? (raw.split('.')[1]?.length ?? 0) : 0
      if (!/^-?\d+(\.\d+)?$/.test(raw) || decimal > precision) {
        fail(text, callback)
        return
      }
      const number = Number(raw)
      if (options.min !== undefined && number < options.min) {
        fail(text, callback)
        return
      }
      if (options.max !== undefined && number > options.max) {
        fail(text, callback)
        return
      }
      pass(callback)
    },
  }
}

/** 数值区间（含边界；空值跳过；非数值失败） */
export function numberRange(min: number, max: number, message?: string): FieldRule {
  const text = message ?? `数值需在 ${min} ~ ${max} 之间`
  return {
    message: text,
    trigger: 'blur',
    validator: (_rule, value, callback) => {
      if (isEmpty(value)) {
        pass(callback)
        return
      }
      const number = typeof value === 'number' ? value : Number(String(value).trim())
      if (!Number.isFinite(number) || number < min || number > max) {
        fail(text, callback)
        return
      }
      pass(callback)
    },
  }
}

/** 编码规则（如点分小写、岗位编码规则；空值跳过） */
export function codePattern(regExp: RegExp, message = '编码格式不正确'): FieldRule {
  return regexRule(regExp, message)
}
