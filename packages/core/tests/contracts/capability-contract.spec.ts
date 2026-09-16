/**
 * 契约测试模板（能力基类）：key 口径 / 依赖登记 / 循环检测 / 元信息。
 */

import { afterEach, describe, expect, it } from 'vitest'

import { BaseCapability, BaseError, registerKnownCapabilities, resetKnownCapabilities } from '../../src'

describe('能力基类契约', () => {
  afterEach(() => {
    resetKnownCapabilities()
  })

  it('合法声明：key 与 depends 落位，describe 元信息齐备（注册项契约）', () => {
    registerKnownCapabilities({ value: [], 'field-shell': [], field: ['value', 'field-shell'] })
    const capability = new BaseCapability({ key: 'field', strict: true })
    expect(capability.key).toBe('field')
    expect(capability.depends).toEqual(['value', 'field-shell'])
    expect(capability.describe()).toEqual({ key: 'field', depends: ['value', 'field-shell'] })
  })

  it('非法 key / 未登记依赖 / 循环依赖：默认告警、strict 抛 10001', () => {
    registerKnownCapabilities({ a: ['b'], b: ['a'] })

    const warnings: string[] = []
    new BaseCapability({ key: 'Bad_Key', onWarn: (message) => warnings.push(message) })
    new BaseCapability({ key: 'x', depends: ['ghost'], onWarn: (message) => warnings.push(message) })
    new BaseCapability({ key: 'a', onWarn: (message) => warnings.push(message) })
    expect(warnings).toHaveLength(3)

    try {
      new BaseCapability({ key: 'a', strict: true })
      expect.unreachable('应抛错')
    } catch (error) {
      expect((error as BaseError).code).toBe(10001)
    }
  })

  it('enabled=false 跳过校验（预览 / 测试用）', () => {
    expect(() => new BaseCapability({ key: 'Bad_Key', enabled: false })).not.toThrow()
  })
})
