/** 注册项 `BaseProvider` 与工厂 `BaseFactory` 用例（02-5）。 */

import { describe, expect, it } from 'vitest'

import { BaseCapability, BaseFactory, BasePluggable, BaseProvider } from '../src'

class DemoProvider extends BaseProvider {
  readonly key = 'demo-provider'
}

class DemoFactory extends BaseFactory<number, string> {
  readonly pluginKey = 'demo-factory'
  readonly pluginName = 'core'

  create(options: number): string {
    return String(options)
  }
}

describe('BaseProvider 注册项（组合轨）', () => {
  it('继承能力域基类而非插件基类', () => {
    const provider = new DemoProvider()
    expect(provider).toBeInstanceOf(BaseCapability)
    expect(provider).not.toBeInstanceOf(BasePluggable)
  })
})

describe('BaseFactory 工厂基类', () => {
  it('创建产出物（可调用 create）', () => {
    const factory = new DemoFactory()
    expect(factory.create(7)).toBe('7')
  })
})
