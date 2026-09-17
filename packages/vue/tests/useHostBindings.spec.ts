/** 宿主投影用例：`useAccess` / `useFrontendBase`（S4c 移动端收口所需的最小面）。 */

import { effectScope, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { useAccess, useFrontendBase } from '../src'

describe('useAccess（投影）', () => {
  it('判定语义与集合联动', async () => {
    const codes = ref<readonly string[]>(['a'])
    const access = effectScope(true).run(() => useAccess({ codes }))!
    expect(access.codes).toEqual(['a'])
    expect(access.has('a')).toBe(true)
    expect(access.hasAll(['a', 'b'])).toBe(false)
    expect(access.hasAny(['b', 'c'])).toBe(false)

    codes.value = ['a', 'b']
    // 同步生效（与旧片段「读即最新」语义一致）
    expect(access.codes).toEqual(['a', 'b'])
    expect(access.hasAll(['a', 'b'])).toBe(true)
    expect(access.hasAny(['c', 'b'])).toBe(true)
    await nextTick()
    expect(access.codes).toEqual(['a', 'b'])
  })

  it('缺省空集；作用域释放取订', async () => {
    const scope = effectScope()
    const access = scope.run(() => useAccess())!
    expect(access.codes).toEqual([])
    expect(access.has('a')).toBe(false)
    scope.stop()
    expect(() => access.has('a')).not.toThrow()
  })
})

describe('useFrontendBase（投影）', () => {
  it('日志与错误上报经注入出口；identifier 原样带回', () => {
    const logs: string[] = []
    const errors: unknown[] = []
    const base = useFrontendBase({
      ns: 'store',
      identifier: 'demo',
      logger: { log: (_level, message) => logs.push(message) },
      errorReporter: (error) => errors.push(error),
    })
    expect(base.ns).toBe('store')
    expect(base.identifier).toBe('demo')
    expect(base.getConfig('missing', 'fallback')).toBe('fallback')

    base.log('info', 'hello')
    expect(logs[0]).toContain('hello')

    const failure = new Error('boom')
    base.reportError(failure, { store: 'demo' })
    expect(errors).toEqual([failure])
  })

  it('作用域释放调用 dispose（幂等不抛错）', () => {
    const scope = effectScope()
    const base = scope.run(() => useFrontendBase({ ns: 'api' }))!
    scope.stop()
    expect(() => base.dispose()).not.toThrow()
  })

  it('缺省静音：log / reportError 不抛错', () => {
    const base = useFrontendBase()
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    base.log('debug', 'x')
    base.reportError(new Error('x'))
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})
