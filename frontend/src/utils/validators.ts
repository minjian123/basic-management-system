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
  message: string
  trigger: 'blur' | 'change'
}

export function required(message = '必填项'): FieldRule {
  return { required: true, message, trigger: 'blur' }
}

export function pattern(regExp: RegExp, message: string): FieldRule {
  return { pattern: regExp, message, trigger: 'blur' }
}
