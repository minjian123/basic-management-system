/** 校验器用例（02-6）。 */

import { describe, expect, it } from 'vitest'

import { amount, codePattern, email, lengthRange, numberRange, phone, required, url } from '../src'

describe('校验器', () => {
  it('必填（不跳过空值）', () => {
    const rule = required()
    expect(rule('')).toBe('必填')
    expect(rule(undefined)).toBe('必填')
    expect(rule('x')).toBeUndefined()
  })

  it('长度范围（空值跳过）', () => {
    const rule = lengthRange(2, 4)
    expect(rule('')).toBeUndefined()
    expect(rule('a')).toContain('2')
    expect(rule('abc')).toBeUndefined()
    expect(rule('abcde')).toContain('2')
  })

  it('邮箱 / 手机号 / URL', () => {
    expect(email()('a@b.com')).toBeUndefined()
    expect(email()('bad')).toBeDefined()
    expect(phone()('13800138000')).toBeUndefined()
    expect(phone()('12345')).toBeDefined()
    expect(url()('https://a.com')).toBeUndefined()
    expect(url()('not-url')).toBeDefined()
  })

  it('金额 / 数值范围 / 编码格式', () => {
    expect(amount()('1.5')).toBeUndefined()
    expect(amount()('-1')).toBeDefined()
    expect(numberRange(1, 10)(5)).toBeUndefined()
    expect(numberRange(1, 10)(11)).toBeDefined()
    expect(codePattern(/^[A-Z]+$/, '须大写')('ABC')).toBeUndefined()
    expect(codePattern(/^[A-Z]+$/, '须大写')('abc')).toBe('须大写')
  })
})
