/** 总基类 `BaseObject` 用例（02-1）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { BaseObject, configureBase, resetBaseSinks } from '../src'

afterEach(() => resetBaseSinks())

describe('BaseObject 总基类', () => {
  it('命名空间与版本（缺省 + 显式）', () => {
    const a = new BaseObject()
    expect([a.namespace, a.version]).toEqual(['base', '0.0.0'])
    const b = new BaseObject('bms', '1.2.3')
    expect([b.namespace, b.version]).toEqual(['bms', '1.2.3'])
  })

  it('日志委托注入 sink（带命名空间前缀）', () => {
    const logger = vi.fn()
    configureBase({ logger })
    new BaseObject('ns').log('warn', 'hello', { a: 1 })
    expect(logger).toHaveBeenCalledWith('warn', '[ns] hello', { a: 1 })
  })

  it('错误上报委托注入 sink', () => {
    const reporter = vi.fn()
    configureBase({ reporter })
    const error = new Error('boom')
    new BaseObject().reportError(error, { where: 'test' })
    expect(reporter).toHaveBeenCalledWith(error, { where: 'test' })
  })

  it('配置读取：注入源命中与 fallback', () => {
    configureBase({ config: { get: (key) => (key === 'a' ? 42 : undefined) } })
    const obj = new BaseObject()
    expect(obj.getConfig('a', 0)).toBe(42)
    expect(obj.getConfig('missing', 'x')).toBe('x')
  })

  it('dispose 幂等且 onDispose 只执行一次', () => {
    let count = 0

    class Probe extends BaseObject {
      protected override onDispose(): void {
        count += 1
      }
    }

    const probe = new Probe()
    expect(probe.isDisposed).toBe(false)
    probe.dispose()
    probe.dispose()
    expect(probe.isDisposed).toBe(true)
    expect(count).toBe(1)
  })
})
