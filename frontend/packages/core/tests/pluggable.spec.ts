/** 插件基类 `BasePluggable` 用例（02-1）。 */

import { describe, expect, it } from 'vitest'

import { BaseCapability, BaseObject, BasePluggable, DEFAULT_CONTRACT_VERSION } from '../src'

class DemoPlugin extends BasePluggable {
  readonly pluginKey = 'demo'
  readonly pluginName = 'core'
}

describe('BasePluggable 插件基类', () => {
  it('继承链 BasePluggable → BaseCapability → BaseObject', () => {
    const demo = new DemoPlugin()
    expect(demo).toBeInstanceOf(BaseCapability)
    expect(demo).toBeInstanceOf(BaseObject)
  })

  it('插件键 / 实现名 / 缺省契约版本 / 能力键 = 插件键', () => {
    const demo = new DemoPlugin()
    expect(demo.pluginKey).toBe('demo')
    expect(demo.pluginName).toBe('core')
    expect(demo.contractVersion).toBe(DEFAULT_CONTRACT_VERSION)
    expect(demo.key).toBe('demo')
  })

  it('describe 含实现名与契约版本', () => {
    expect(new DemoPlugin().describe()).toBe(`demo:core@${DEFAULT_CONTRACT_VERSION}`)
  })

  it('setup 缺省空实现（可调用）', () => {
    expect(() => new DemoPlugin().setup()).not.toThrow()
  })
})
