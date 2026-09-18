/** Vue 绑定投影用例（02_07 / 02_06 宿主前置）。 */

import { effectScope } from 'vue'
import { describe, expect, it } from 'vitest'

import { BaseAccess, BaseValue } from '@bms/core'

import { useAccess, useValue } from '../src'

class DemoValue extends BaseValue<number> {}
class DemoAccess extends BaseAccess {}

describe('useValue 投影', () => {
  it('响应值 / 空态 / 取消订阅', () => {
    const source = new DemoValue()
    const scope = effectScope()
    const result = scope.run(() => useValue(source))!

    expect(result.value.value).toBeUndefined()
    expect(result.isEmpty.value).toBe(true)

    result.setValue(1)
    expect(result.value.value).toBe(1)
    expect(result.isEmpty.value).toBe(false)

    scope.stop()
    source.setValue(2)
    expect(result.value.value).toBe(1)
  })
})

describe('useAccess 投影', () => {
  it('权限判定', () => {
    const source = new DemoAccess()
    source.setCodes(['a', 'b'])
    const access = useAccess(source)
    expect(access.has('a')).toBe(true)
    expect(access.hasAny(['x', 'b'])).toBe(true)
    expect(access.hasAll(['a', 'b'])).toBe(true)
    expect(access.codes.value).toEqual(['a', 'b'])
  })
})
