/** 异步资源基类用例（Kiwi 702）：登记 / 逆序释放 / 幂等 / 释放钩子 / 句柄归一化（双端同款）。 */

import { beforeEach, describe, expect, it } from 'vitest'
import { effectScope, nextTick } from 'vue'

import { BaseComponent, resetMechanismWarnings, type MechanismRegistry } from '@/base/BaseComponent'
import { resetFrontendBaseConfig, setFrontendSinks, type LogRecord } from '@/base/BaseFrontend'
import { BaseAsyncResource, RESOURCE_MECHANISM_KEY, useAsyncResourceBase } from '@/base/resource'

/** 探针组件根：验证机制装配点 */
class ProbeRoot extends BaseComponent {}

const logRecords: LogRecord[] = []

/** 警告记录（断言未知句柄 / 释放后登记告警） */
function warnings(): LogRecord[] {
  return logRecords.filter((record) => record.level === 'warn')
}

beforeEach(() => {
  resetFrontendBaseConfig()
  resetMechanismWarnings()
  logRecords.length = 0
  setFrontendSinks({
    log: (record) => logRecords.push(record),
    error: () => {},
  })
})

describe('异步资源基类（Kiwi 702）', () => {
  it('⑮ track 句柄归一化：函数 / AbortController / dispose / destroy / 定时器 id', () => {
    const resource = new BaseAsyncResource({ ns: 'probe' })
    const calls: string[] = []

    const releaseFunction = resource.track(() => calls.push('function'))
    expect(resource.count).toBe(1)

    const controller = new AbortController()
    resource.track(controller, 'request')
    expect(resource.count).toBe(2)

    const disposable = {
      dispose: () => calls.push('dispose'),
    }
    resource.track(disposable)

    const destroyable = {
      destroy: () => calls.push('destroy'),
    }
    resource.track(destroyable)

    const timerId = setTimeout(() => calls.push('timer-fired'), 1000)
    resource.track(timerId, 'timer')
    expect(resource.count).toBe(5)

    resource.releaseAll()
    expect(calls).toEqual(['destroy', 'dispose', 'function'])
    expect(controller.signal.aborted).toBe(true)
    expect(resource.count).toBe(0)

    // 单独释放函数幂等
    releaseFunction()
    expect(calls.filter((call) => call === 'function')).toHaveLength(1)
  })

  it('⑯ releaseAll 逆序释放，释放钩子在资源之后逆序执行', () => {
    const resource = new BaseAsyncResource({ ns: 'probe' })
    const order: string[] = []
    resource.track(() => order.push('first'))
    resource.track(() => order.push('second'))
    resource.onRelease(() => order.push('hook-1'))
    resource.onRelease(() => order.push('hook-2'))

    resource.releaseAll()
    expect(order).toEqual(['second', 'first', 'hook-2', 'hook-1'])
    expect(resource.count).toBe(0)

    // 重复释放无副作用
    resource.releaseAll()
    expect(order).toHaveLength(4)
  })

  it('⑰ 释放幂等、释放后拒绝登记并开发态告警；未知句柄只告警', () => {
    const resource = new BaseAsyncResource({ ns: 'probe' })
    const unknown = resource.track({} as never)
    expect(resource.count).toBe(0)
    expect(warnings().some((record) => record.message.includes('未知句柄类型'))).toBe(true)

    let released = 0
    resource.track(() => {
      released += 1
    })
    unknown()
    resource.dispose()
    expect(resource.released).toBe(true)
    expect(released).toBe(1)

    resource.dispose()
    expect(released).toBe(1)

    resource.track(() => {})
    expect(resource.count).toBe(0)
    expect(warnings().some((record) => record.message.includes('已释放，拒绝登记'))).toBe(true)
  })

  it('⑱ 单资源释放失败不阻断其余资源（onError 回调）', () => {
    const errors: unknown[] = []
    const resource = new BaseAsyncResource({ ns: 'probe', onError: (error) => errors.push(error) })
    const order: string[] = []
    resource.track(() => order.push('first'))
    resource.track(() => {
      throw new Error('release-failed')
    })
    resource.track(() => order.push('third'))

    expect(() => resource.releaseAll()).not.toThrow()
    expect(order).toEqual(['third', 'first'])
    expect(errors).toHaveLength(1)
    expect(resource.count).toBe(0)
  })

  it('⑲ addTimer / addAbort / addDisposer 便捷入口', async () => {
    const resource = new BaseAsyncResource({ ns: 'probe' })
    const ticks: string[] = []
    resource.addTimer(() => ticks.push('timeout'), 1)
    resource.addTimer(() => ticks.push('interval'), 1, { repeat: true })
    const controller = resource.addAbort()
    resource.addDisposer(() => ticks.push('disposer'))
    expect(resource.count).toBe(4)

    await new Promise((resolve) => setTimeout(resolve, 5))
    expect(ticks).toContain('timeout')
    expect(ticks).toContain('interval')

    resource.releaseAll()
    expect(controller.signal.aborted).toBe(true)
    expect(ticks).toContain('disposer')
    const intervalTicks = ticks.filter((tick) => tick === 'interval').length
    await new Promise((resolve) => setTimeout(resolve, 5))
    expect(ticks.filter((tick) => tick === 'interval')).toHaveLength(intervalTicks)
  })

  it('⑳ 组合式随作用域释放；owner 装配与 mechanism 入口', async () => {
    const scope = effectScope()
    const resource = scope.run(() => useAsyncResourceBase({ ns: 'probe', kind: 'request', owner: undefined }))
    expect(resource).toBeDefined()
    let released = 0
    resource?.track(() => {
      released += 1
    })
    expect(resource?.count).toBe(1)
    scope.stop()
    await nextTick()
    expect(released).toBe(1)
    expect(resource?.released).toBe(true)

    // owner 装配：进入组件根装配点，且不产生未挂接告警
    resetMechanismWarnings()
    logRecords.length = 0
    const root = new ProbeRoot()
    const attached = new BaseAsyncResource({ ns: 'probe', owner: root })
    attached.track(() => {})
    expect(root.mechanisms.get(RESOURCE_MECHANISM_KEY)).toBe(attached)
    expect(warnings()).toHaveLength(0)

    const registry: MechanismRegistry = root.mechanisms
    registry.detach(attached)
    expect(registry.size).toBe(0)
  })
})
