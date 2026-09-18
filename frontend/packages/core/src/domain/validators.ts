/**
 * 领域纯函数：通用校验器（空值跳过、必填独立）。
 *
 * 校验器签名与 `capabilities/validatable.ts` 的 `Validator<T>` 一致，可直接装入规则链。
 */

import type { Validator } from '../capabilities/validatable'

/** 是否为空值（`null` / `undefined` / 空字符串）。 */
function isEmpty(value: unknown): boolean {
  return value == null || value === ''
}

/**
 * 必填校验（不跳过空值）。
 *
 * @param message 错误文案。
 */
export function required(message = '必填'): Validator<unknown> {
  return (value) => (isEmpty(value) ? message : undefined)
}

/**
 * 长度范围校验。
 *
 * @param min 最小长度。
 * @param max 最大长度。
 * @param message 错误文案。
 */
export function lengthRange(min: number, max: number, message?: string): Validator<string> {
  return (value) => {
    if (isEmpty(value)) {
      return undefined
    }
    const length = String(value).length
    return length < min || length > max ? (message ?? `长度须为 ${min} ~ ${max}`) : undefined
  }
}

/**
 * 邮箱校验。
 *
 * @param message 错误文案。
 */
export function email(message = '邮箱格式不正确'): Validator<string> {
  const pattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return (value) => (isEmpty(value) || pattern.test(String(value)) ? undefined : message)
}

/**
 * 手机号校验（中国大陆）。
 *
 * @param message 错误文案。
 */
export function phone(message = '手机号格式不正确'): Validator<string> {
  const pattern = /^1[3-9]\d{9}$/
  return (value) => (isEmpty(value) || pattern.test(String(value)) ? undefined : message)
}

/**
 * URL 校验。
 *
 * @param message 错误文案。
 */
export function url(message = 'URL 格式不正确'): Validator<string> {
  return (value) => {
    if (isEmpty(value)) {
      return undefined
    }
    try {
      // 仅用 URL 构造做合法判定
      void new URL(String(value))
      return undefined
    } catch {
      return message
    }
  }
}

/**
 * 金额校验（正数）。
 *
 * @param message 错误文案。
 */
export function amount(message = '金额须为正数'): Validator<string | number> {
  return (value) => {
    if (isEmpty(value)) {
      return undefined
    }
    const num = Number(value)
    return Number.isFinite(num) && num > 0 ? undefined : message
  }
}

/**
 * 数值范围校验。
 *
 * @param min 最小值。
 * @param max 最大值。
 * @param message 错误文案。
 */
export function numberRange(min: number, max: number, message?: string): Validator<number> {
  return (value) => {
    if (isEmpty(value)) {
      return undefined
    }
    const num = Number(value)
    return num >= min && num <= max ? undefined : (message ?? `须在 ${min} ~ ${max} 之间`)
  }
}

/**
 * 编码格式校验（自定义正则）。
 *
 * @param pattern 正则。
 * @param message 错误文案。
 */
export function codePattern(pattern: RegExp, message: string): Validator<string> {
  return (value) => (isEmpty(value) || pattern.test(String(value)) ? undefined : message)
}
