/** 异步资源 / 订阅用例（02-5）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { BaseAsyncResource, BaseError, BaseSubscription, configureBase, resetBaseSinks } from '../src'

afterEach(() => resetBaseSinks())

class ProbeResource extends BaseAsyncResource {
  readonly order: string[] = []

  add(name: string): void {
    this.registerDisposable({ dispose: () => this.order.push(name) })
  }

  addFailing(): void {
    this.registerDisposable({
      dispose: () => {
        throw new Error('boom')
      },
    })
  }
}

class ProbeSubscription extends BaseSubscription {
  readonly events: string[] = []

  subscribe(onUnsubscribe: () => void): void {
    this.registerUnsubscribe(onUnsubscribe)
  }
}

describe('BaseAsyncResource 异步资源基座', () => {
  it('逆序释放', () => {
    const resource = new ProbeResource()
    resource.add('a')
    resource.add('b')
    resource.dispose()
    expect(resource.order).toEqual(['b', 'a'])
  })

  it('释放后拒绝登记', () => {
    const resource = new ProbeResource()
    resource.dispose()
    expect(() => resource.add('x')).toThrow(BaseError)
  })

  it('单个失败不阻断其余释放（并上报）', () => {
    const reporter = vi.fn()
    configureBase({ reporter })
    const resource = new ProbeResource()
    resource.add('a')
    resource.addFailing()
    resource.add('c')
    resource.dispose()
    expect(resource.order).toEqual(['c', 'a'])
    expect(reporter).toHaveBeenCalled()
  })
})

describe('BaseSubscription 订阅基座', () => {
  it('取消函数随释放自动调用', () => {
    const resource = new ProbeSubscription()
    const unsubscribe = vi.fn()
    resource.subscribe(unsubscribe)
    expect(unsubscribe).not.toHaveBeenCalled()
    resource.dispose()
    expect(unsubscribe).toHaveBeenCalledOnce()
  })
})
