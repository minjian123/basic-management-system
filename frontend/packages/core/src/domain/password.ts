/**
 * 密码强度评估（框架无关核心领域层）：纯函数、无副作用（不落日志 / 不作存储）。
 *
 * 规则可配，`ui-ep` / `ui-vant` 只做展示包装 —— 双端同一套判定口径。
 */

export type PasswordStrengthLevel = 'weak' | 'medium' | 'strong'

/** 缺失项（供提示逐项展示） */
export type PasswordStrengthMissing = 'length' | 'lower' | 'upper' | 'digit' | 'symbol'

export interface PasswordStrengthRules {
  /** 最小长度（默认 8） */
  minLength?: number
  /** 强密码最小长度（默认 12） */
  strongLength?: number
  /** 中等强度最小字符类别数（默认 2：小写 / 大写 / 数字 / 符号） */
  mediumClasses?: number
  /** 强密码最小字符类别数（默认 3） */
  strongClasses?: number
}

export interface PasswordStrengthResult {
  level: PasswordStrengthLevel
  /** 0 ~ 4（长度与字符类别综合，供进度展示） */
  score: number
  missing: readonly PasswordStrengthMissing[]
}

export const defaultPasswordStrengthRules: Required<PasswordStrengthRules> = {
  minLength: 8,
  strongLength: 12,
  mediumClasses: 2,
  strongClasses: 3,
}

/** 符号 = 非字母数字字符 */
const SYMBOL_PATTERN = /[^A-Za-z0-9]/

export function evaluatePasswordStrength(
  value: string | null | undefined,
  rules: PasswordStrengthRules = {},
): PasswordStrengthResult {
  const resolved = { ...defaultPasswordStrengthRules, ...rules }
  const text = typeof value === 'string' ? value : ''
  if (text.length === 0) {
    return { level: 'weak', score: 0, missing: ['length', 'lower', 'upper', 'digit', 'symbol'] }
  }

  const hasLower = /[a-z]/.test(text)
  const hasUpper = /[A-Z]/.test(text)
  const hasDigit = /\d/.test(text)
  const hasSymbol = SYMBOL_PATTERN.test(text)
  const classCount = [hasLower, hasUpper, hasDigit, hasSymbol].filter(Boolean).length

  const missing: PasswordStrengthMissing[] = []
  if (text.length < resolved.minLength) {
    missing.push('length')
  }
  if (!hasLower) {
    missing.push('lower')
  }
  if (!hasUpper) {
    missing.push('upper')
  }
  if (!hasDigit) {
    missing.push('digit')
  }
  if (!hasSymbol) {
    missing.push('symbol')
  }

  const lengthScore = text.length >= resolved.strongLength ? 2 : text.length >= resolved.minLength ? 1 : 0
  const score = Math.min(4, lengthScore + classCount)

  let level: PasswordStrengthLevel = 'weak'
  if (text.length >= resolved.strongLength && classCount >= resolved.strongClasses) {
    level = 'strong'
  } else if (text.length >= resolved.minLength && classCount >= resolved.mediumClasses) {
    level = 'medium'
  }

  return { level, score, missing }
}
