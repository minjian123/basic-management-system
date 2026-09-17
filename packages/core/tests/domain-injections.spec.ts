/** 领域层用例：四个注入共享工厂（语义）+ 契约工厂自身可跑（探针默认，不触发真实 UI）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createConfirmService,
  createMenuSourceService,
  createPermissionGate,
  createViewResolverService,
} from '../src'
import { describeConfirmContract, describePermissionContract } from '../testing'

const probeDefault = vi.fn(async () => true)

afterEach(() => {
  vi.restoreAllMocks()
  probeDefault.mockClear()
})

describe('确认服务工厂', () => {
  it('未覆盖走默认；覆盖与恢复语义', async () => {
    const service = createConfirmService(probeDefault)
    await expect(service.confirm({ message: 'a' })).resolves.toBe(true)
    expect(probeDefault).toHaveBeenCalledTimes(1)

    const override = vi.fn(async () => false)
    service.configure(override)
    await expect(service.confirm({ message: 'b' })).resolves.toBe(false)
    expect(probeDefault).toHaveBeenCalledTimes(1)
    expect(override).toHaveBeenCalledWith({ message: 'b' })

    service.configure(undefined)
    await expect(service.confirm({ message: 'c' })).resolves.toBe(true)
    expect(probeDefault).toHaveBeenCalledTimes(2)
  })
})

describe('确认服务契约（对共享工厂执行工厂断言）', () => {
  describeConfirmContract(createConfirmService(probeDefault))
})

const permissionGate = createPermissionGate()

describe('权限判定契约（对共享工厂执行工厂断言）', () => {
  describePermissionContract(permissionGate)
})

describe('权限判定工厂（语义补充）', () => {
  it('判定器收到归一数组与 mode；空码不经过判定器', () => {
    const gate = createPermissionGate()
    const checker = vi.fn(() => true)
    gate.configure(checker)
    expect(gate.check('a')).toBe(true)
    expect(checker).toHaveBeenLastCalledWith(['a'], 'any')
    gate.check(['a', 'b'], 'all')
    expect(checker).toHaveBeenLastCalledWith(['a', 'b'], 'all')
    gate.check(null)
    gate.check([])
    expect(checker).toHaveBeenCalledTimes(2)
  })
})

describe('菜单状态工厂', () => {
  it('未注入为空；覆盖与恢复', () => {
    const service = createMenuSourceService()
    expect(service.get()).toBeUndefined()
    const provider = {
      visibleMenus: () => [],
      expandedKeys: () => [],
      setExpanded: () => {},
      expandByPath: () => {},
    }
    service.configure(provider)
    expect(service.get()).toBe(provider)
    service.configure(undefined)
    expect(service.get()).toBeUndefined()
  })
})

describe('视图解析工厂', () => {
  it('未注入返回 null；覆盖与恢复（泛型 TView）', () => {
    const service = createViewResolverService<string>()
    expect(service.resolve('Home')).toBeNull()
    service.configure((name) => `view:${name}`)
    expect(service.resolve('Home')).toBe('view:Home')
    service.configure(() => null)
    expect(service.resolve('Home')).toBeNull()
    service.configure(undefined)
    expect(service.resolve('Home')).toBeNull()
  })
})
