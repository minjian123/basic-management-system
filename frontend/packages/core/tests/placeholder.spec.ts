/** 占位三件用例（02-5）。 */

import { describe, expect, it } from 'vitest'

import { BaseError, BaseNullObject, BasePlaceholder, BaseStub } from '../src'

class NullThing extends BaseNullObject {
  noop(): void {}
}

class StubThing extends BaseStub {
  run(): never {
    return this.notImplemented('run')
  }
}

describe('占位三件', () => {
  it('空实现：占位标记 + reason=null + 无副作用', () => {
    const thing = new NullThing()
    expect(thing).toBeInstanceOf(BasePlaceholder)
    expect(thing.placeholder).toBe(true)
    expect(thing.reason).toBe('null')
    expect(() => thing.noop()).not.toThrow()
    expect(thing.describe()).toContain('null')
  })

  it('未实现桩：调用抛 BaseError(NOT_IMPLEMENTED)', () => {
    const thing = new StubThing()
    expect(thing.reason).toBe('stub')
    try {
      thing.run()
      throw new Error('should throw')
    } catch (error) {
      expect(error).toBeInstanceOf(BaseError)
      expect((error as BaseError).code).toBe(19001)
    }
  })
})
