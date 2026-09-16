/**
 * S2 能力矩阵契约：31 项清单一致（manifest ↔ 机制登记 ↔ 注册表 → 可创建）。
 */

import { describe, expect, it } from 'vitest'

import { BaseCapability, capabilityManifest, capabilityRegistry, createCapability, knownCapabilitiesView } from '../../src'

const KEYS = Object.keys(capabilityManifest)

describe('S2 能力矩阵契约（31 项）', () => {
  it('清单规模与分组：值·字段链 4 / 形态 7 / 复用 20 = 31', () => {
    expect(KEYS).toHaveLength(31)
    expect(KEYS).toEqual(
      expect.arrayContaining(['value', 'field-shell', 'field-perm', 'field', 'interactive', 'media', 'layout', 'tabs', 'fragment-context']),
    )
  })

  it('机制登记表与清单一致（knownCapabilitiesView = manifest）', () => {
    expect(knownCapabilitiesView()).toEqual({ ...capabilityManifest })
  })

  it('注册表 31 项全量登记且可创建（key / depends 一致，不注册不可用不再触发）', () => {
    expect(capabilityRegistry.count).toBe(31)
    for (const key of KEYS) {
      const instance = createCapability(key, { enabled: false } as object)
      expect(instance).toBeInstanceOf(BaseCapability)
      expect(instance.key).toBe(key)
      expect([...instance.depends]).toEqual([...(capabilityManifest[key] ?? [])])
      expect(instance.describe().key).toBe(key)
    }
  })

  it('依赖方向为登记内单向（无幽灵依赖）', () => {
    for (const [key, depends] of Object.entries(capabilityManifest)) {
      for (const dependency of depends) {
        expect(KEYS, `${key} → ${dependency}`).toContain(dependency)
      }
    }
  })
})
