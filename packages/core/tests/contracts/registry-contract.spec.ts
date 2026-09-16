/**
 * 契约测试模板（注册表）：所有注册表实现（Null / 内存 / 真实）跑同一套断言。
 *
 * 模板形态——新增实现只在 `IMPLEMENTATIONS` 登记后自动纳入契约覆盖（同后端契约套件口径）。
 */

import { describe, expect, it } from 'vitest'

import { BaseError, BaseRegistry, ProviderRegistry, requireProvider, type RegistryItemLike } from '../../src'

function makeItem(key: string): RegistryItemLike {
  return { key, describe: () => ({ key }) }
}

interface RegistryImplementation {
  name: string
  create: () => BaseRegistry<RegistryItemLike>
}

/** 实现清单（新增实现登记于此） */
const IMPLEMENTATIONS: RegistryImplementation[] = [
  { name: 'BaseRegistry', create: () => new BaseRegistry() },
  { name: 'ProviderRegistry', create: () => new ProviderRegistry() },
]

describe.each(IMPLEMENTATIONS)('注册表契约：$name', ({ create }) => {
  it('注册与读取：get 命中 / 未命中返回 undefined', () => {
    const registry = create()
    registry.register(makeItem('a'))
    expect(registry.get('a')?.key).toBe('a')
    expect(registry.get('missing')).toBeUndefined()
  })

  it('唯一性：默认告警保留首个；strict 抛 BaseError(10003)', () => {
    const registry = create()
    const warnings: string[] = []
    registry.register(makeItem('a'))
    registry.register(makeItem('a'), { onWarn: (message) => warnings.push(message) })
    expect(warnings).toHaveLength(1)
    expect(registry.count).toBe(1)

    expect(() => registry.register(makeItem('a'), { strict: true })).toThrowError(BaseError)
    try {
      registry.register(makeItem('a'), { strict: true })
    } catch (error) {
      expect((error as BaseError).code).toBe(10003)
    }
  })

  it('保序与快照：keys / values 插入序；snapshot 只读', () => {
    const registry = create()
    registry.register(makeItem('b'))
    registry.register(makeItem('a'))
    expect(registry.keys()).toEqual(['b', 'a'])
    expect(registry.values().map((item) => item.key)).toEqual(['b', 'a'])
    const snapshot = registry.snapshot()
    expect(Object.isFrozen(snapshot)).toBe(true)
    expect(Object.keys(snapshot)).toEqual(['b', 'a'])
  })

  it('不注册不可用：requireProvider 未命中抛 BaseError(10002)', () => {
    const registry = new ProviderRegistry()
    registry.register(makeItem('exist'))
    expect(requireProvider(registry, 'exist').key).toBe('exist')
    expect(() => requireProvider(registry, 'absent')).toThrowError(BaseError)
    try {
      requireProvider(registry, 'absent')
    } catch (error) {
      expect((error as BaseError).code).toBe(10002)
    }
  })
})
