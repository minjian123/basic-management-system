/** 布尔域纯函数契约（`05_03`）：后端 `SMALLINT` 1/0 与字面量的归一口径。 */

import { describe, expect, it } from 'vitest'

import { normalizeBooleanValue } from '../../src'

describe('布尔域纯函数', () => {
  it('布尔字面量原样返回', () => {
    expect(normalizeBooleanValue(true)).toBe(true)
    expect(normalizeBooleanValue(false)).toBe(false)
  })

  it('数字 1 / 0 归一（其余数字视为无法识别）', () => {
    expect(normalizeBooleanValue(1)).toBe(true)
    expect(normalizeBooleanValue(0)).toBe(false)
    expect(normalizeBooleanValue(2)).toBeNull()
    expect(normalizeBooleanValue(-1)).toBeNull()
  })

  it('字符串字面量归一（忽略大小写与首尾空格）', () => {
    expect(normalizeBooleanValue('1')).toBe(true)
    expect(normalizeBooleanValue('0')).toBe(false)
    expect(normalizeBooleanValue('true')).toBe(true)
    expect(normalizeBooleanValue('FALSE')).toBe(false)
    expect(normalizeBooleanValue(' true ')).toBe(true)
    expect(normalizeBooleanValue('yes')).toBeNull()
  })

  it('空值与无法识别值 → null（`0` / `false` 不被空值吞掉）', () => {
    expect(normalizeBooleanValue(null)).toBeNull()
    expect(normalizeBooleanValue(undefined)).toBeNull()
    expect(normalizeBooleanValue('')).toBeNull()
    expect(normalizeBooleanValue('   ')).toBeNull()
    expect(normalizeBooleanValue({})).toBeNull()
    expect(normalizeBooleanValue([])).toBeNull()
    expect(normalizeBooleanValue(0)).toBe(false)
    expect(normalizeBooleanValue('0')).toBe(false)
  })
})
