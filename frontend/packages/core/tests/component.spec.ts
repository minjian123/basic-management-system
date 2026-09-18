/** 组件根 `BaseComponent` 用例（02-2）。 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  BaseCapability,
  BaseComponent,
  BaseObject,
  BasePluggable,
  configureBase,
  resetBaseSinks,
} from '../src'

afterEach(() => resetBaseSinks())

class DemoBox extends BaseComponent {
  readonly identifier = 'demo-box'

  mountMechanismForTest(name: string, mechanism: unknown): void {
    this.mountMechanism(name, mechanism)
  }
}

describe('BaseComponent 组件根', () => {
  it('继承链 BaseComponent → BasePluggable → BaseCapability → BaseObject', () => {
    const box = new DemoBox()
    expect(box).toBeInstanceOf(BasePluggable)
    expect(box).toBeInstanceOf(BaseCapability)
    expect(box).toBeInstanceOf(BaseObject)
  })

  it('标识 / 插件键 / 命名空间类名', () => {
    const box = new DemoBox()
    expect(box.identifier).toBe('demo-box')
    expect(box.pluginKey).toBe('demo-box')
    expect(box.key).toBe('demo-box')
    expect(box.nsClass).toBe('bms-demo-box')
  })

  it('令牌属性协议与状态类（随档位 / 状态变化）', () => {
    const box = new DemoBox()
    expect(box.rootAttrs()).toEqual({ 'data-size': 'default', 'data-density': 'default' })
    expect(box.stateClasses()).toEqual([])

    box.setProps({ size: 'large', density: 'compact', loading: true, disabled: true, visible: false })
    expect(box.rootAttrs()).toEqual({
      'data-size': 'large',
      'data-density': 'compact',
      'aria-busy': 'true',
      'aria-disabled': 'true',
      'aria-hidden': 'true',
    })
    expect(box.stateClasses()).toEqual(['is-loading', 'is-disabled', 'is-hidden'])
  })

  it('attrs 透传：过滤保留键与下划线前缀，其余照常', () => {
    const box = new DemoBox()
    expect(
      box.passthroughAttrs({ size: 'large', _internal: 1, class: 'x', 'data-k': 2, 'aria-label': 'y' }),
    ).toEqual({ class: 'x', 'data-k': 2, 'aria-label': 'y' })
  })

  it('生命周期：多监听 / 取消幂等 / 释放广播 unmount', () => {
    const box = new DemoBox()
    const seen: string[] = []
    const off1 = box.onLifecycle((event) => seen.push(`a:${event}`))
    box.onLifecycle((event) => seen.push(`b:${event}`))

    box.setProps({ loading: true })
    expect(seen).toEqual(['a:update', 'b:update'])

    off1()
    off1()
    box.notifyLifecycle('mount')
    expect(seen).toEqual(['a:update', 'b:update', 'b:mount'])

    box.dispose()
    expect(seen).toContain('b:unmount')
  })

  it('监听器异常上报且不阻断其余', () => {
    const reporter = vi.fn()
    configureBase({ reporter })
    const box = new DemoBox()
    const second = vi.fn()
    box.onLifecycle(() => {
      throw new Error('listener boom')
    })
    box.onLifecycle(second)
    box.notifyLifecycle('mount')
    expect(second).toHaveBeenCalledOnce()
    expect(reporter).toHaveBeenCalled()
  })

  it('机制装配点', () => {
    const box = new DemoBox()
    box.mountMechanismForTest('tabs', { open: true })
    expect(box.mechanisms.get('tabs')).toEqual({ open: true })
    box.dispose()
    expect(box.mechanisms.size).toBe(0)
  })
})
