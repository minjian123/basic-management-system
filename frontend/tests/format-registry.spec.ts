/** 格式化器注册与校验器用例（Kiwi 722）：注册表 / 展示接入 / 规则（双端同款）。 */

import { afterEach, describe, expect, it } from 'vitest'

import { resetFormatters, resolveFormatter, registerFormatter } from '@/components/base/formatters'
import { useDisplayBase } from '@/components/base'
import { amount, codePattern, email, lengthRange, numberRange, phone, url, type FieldRule } from '@/utils/validators'
import { resetFormatDefaults } from '@/utils/format'

/** 直跑规则 validator（模拟 el-form / Vant 回调） */
function validate(rule: FieldRule, value: unknown): string | undefined {
  let error: Error | undefined
  rule.validator?.(null, value, (next) => {
    error = next
  })
  return error?.message
}

describe('格式化器注册与校验器（Kiwi 722）', () => {
  afterEach(() => {
    resetFormatters()
    resetFormatDefaults()
  })

  it('① 内置注册表解析；未注册返回 undefined', () => {
    expect(resolveFormatter('amount')).toBeTypeOf('function')
    expect(resolveFormatter('number')).toBeTypeOf('function')
    expect(resolveFormatter('percent')).toBeTypeOf('function')
    expect(resolveFormatter('date')).toBeTypeOf('function')
    expect(resolveFormatter('datetime')).toBeTypeOf('function')
    expect(resolveFormatter('boolean')).toBeTypeOf('function')
    expect(resolveFormatter('ghost')).toBeUndefined()
  })

  it('② useDisplayBase 名称分发：内置命中 / 未注册回退 String', () => {
    expect(useDisplayBase({ value: 1234.5, formatter: 'amount' }).displayText).toBe('¥1,234.50')
    expect(useDisplayBase({ value: '2026-09-11T06:30:45Z', formatter: 'date', timezone: 'UTC' }).displayText).toBe(
      '2026-09-11',
    )
    expect(useDisplayBase({ value: true, formatter: 'boolean' }).displayText).toBe('是')
    expect(useDisplayBase({ value: 5, formatter: 'ghost' }).displayText).toBe('5')
  })

  it('③ registerFormatter 业务扩展与覆盖；④ resetFormatters 复位', () => {
    registerFormatter('upper', (value) => String(value).toUpperCase())
    expect(useDisplayBase({ value: 'abc', formatter: 'upper' }).displayText).toBe('ABC')

    registerFormatter('amount', () => '覆盖值')
    expect(useDisplayBase({ value: 1, formatter: 'amount' }).displayText).toBe('覆盖值')

    resetFormatters()
    expect(resolveFormatter('upper')).toBeUndefined()
    expect(useDisplayBase({ value: 1234.5, formatter: 'amount' }).displayText).toBe('¥1,234.50')
  })

  it('⑤ lengthRange：空值跳过 / 边界', () => {
    const rule = lengthRange(2, 4)
    expect(validate(rule, '')).toBeUndefined()
    expect(validate(rule, 'a')).toBe(rule.message)
    expect(validate(rule, 'ab')).toBeUndefined()
    expect(validate(rule, 'abcd')).toBeUndefined()
    expect(validate(rule, 'abcde')).toBe(rule.message)
  })

  it('⑥ email / phone / url 规则', () => {
    expect(validate(email(), 'a@b.com')).toBeUndefined()
    expect(validate(email(), 'bad')).toBe(email().message)
    expect(validate(email(), '')).toBeUndefined()

    expect(validate(phone(), '13812345678')).toBeUndefined()
    expect(validate(phone(), '12345')).toBe(phone().message)

    expect(validate(url(), 'https://a.com/x')).toBeUndefined()
    expect(validate(url(), 'ftp://a')).toBe(url().message)
  })

  it('⑦ amount：精度与区间；⑧ numberRange；⑨ codePattern', () => {
    const precision = amount({ precision: 2 })
    expect(validate(precision, '12.30')).toBeUndefined()
    expect(validate(precision, '12.345')).toBe(precision.message)
    expect(validate(precision, '')).toBeUndefined()

    const ranged = amount({ min: 0, max: 100 }, '金额需在 0 ~ 100')
    expect(validate(ranged, '0')).toBeUndefined()
    expect(validate(ranged, '100')).toBeUndefined()
    expect(validate(ranged, '100.01')).toBe(ranged.message)
    expect(validate(ranged, '-5')).toBe(ranged.message)

    const number = numberRange(1, 10)
    expect(validate(number, 1)).toBeUndefined()
    expect(validate(number, 10)).toBeUndefined()
    expect(validate(number, 0)).toBe(number.message)
    expect(validate(number, 'abc')).toBe(number.message)
    expect(validate(number, '')).toBeUndefined()

    const code = codePattern(/^[a-z]+(\.[a-z]+)*$/)
    expect(validate(code, 'sys.config')).toBeUndefined()
    expect(validate(code, 'SysConfig')).toBe(code.message)
    expect(validate(code, '')).toBeUndefined()
  })
})
