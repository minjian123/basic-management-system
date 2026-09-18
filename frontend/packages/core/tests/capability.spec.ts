/** 能力域基类 `BaseCapability` 用例（02-1）。 */

import { describe, expect, it } from 'vitest'

import { BaseCapability, BaseObject } from '../src'

class DemoCapability extends BaseCapability {
  readonly key = 'demo'
  readonly depends = ['value']
}

describe('BaseCapability 能力域基类', () => {
  it('继承总基类', () => {
    expect(new DemoCapability()).toBeInstanceOf(BaseObject)
  })

  it('能力键 / 依赖 / describe', () => {
    const demo = new DemoCapability()
    expect(demo.key).toBe('demo')
    expect(demo.depends).toEqual(['value'])
    expect(demo.describe()).toContain('demo')
  })
})
