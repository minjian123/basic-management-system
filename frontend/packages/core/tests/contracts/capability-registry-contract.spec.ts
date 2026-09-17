/**
 * 契约测试（能力注册表 · 不注册不可用）：登记 / 创建 / 未注册拦截 / 重复拒重 / 清单一致。
 */

import { describe, expect, it } from 'vitest'

import {
  BaseError,
  BaseValue,
  CapabilityRegistry,
  capabilityManifest,
  createCapability,
  knownCapabilitiesView,
} from '../../src'

describe('能力注册表契约（不注册不可用）', () => {
  it('登记后可创建（value / field 链）', () => {
    const value = createCapability('value', { initial: 'a' })
    expect(value).toBeInstanceOf(BaseValue)
    expect((value as BaseValue<string>).getValue()).toBe('a')

    const field = createCapability('field', { shell: { required: true } })
    expect(field.key).toBe('field')
    expect(field.depends).toEqual(['value', 'field-shell', 'field-perm'])
  })

  it('未注册不可用：createCapability 抛 BaseError(10002)', () => {
    try {
      createCapability('ghost')
      expect.unreachable('应抛错')
    } catch (error) {
      expect(error).toBeInstanceOf(BaseError)
      expect((error as BaseError).code).toBe(10002)
    }
  })

  it('重复登记：默认告警保留首个；strict 抛 BaseError(10003)', () => {
    const registry = new CapabilityRegistry()
    const registration = {
      key: 'probe',
      depends: [],
      describe: () => ({ key: 'probe' }),
      create: (options: { key: string }) => new BaseValue({ ...options, key: 'value' }),
    }
    const warnings: string[] = []
    registry.register(registration, { onWarn: (message) => warnings.push(message) })
    registry.register(registration, { onWarn: (message) => warnings.push(message) })
    expect(warnings).toHaveLength(1)
    expect(registry.count).toBe(1)

    try {
      registry.register(registration, { strict: true })
      expect.unreachable('应抛错')
    } catch (error) {
      expect((error as BaseError).code).toBe(10003)
    }
  })

  it('能力清单与机制登记表一致（manifest 权威）', () => {
    expect(knownCapabilitiesView()).toEqual({ ...capabilityManifest })
    expect(Object.keys(capabilityManifest)).toEqual(
      expect.arrayContaining(['value', 'field-shell', 'field-perm', 'field']),
    )
  })
})
