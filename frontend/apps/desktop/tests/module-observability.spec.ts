// kiwi_id: 982
/**
 * 宿主观测用例：错误上报带模块名与版本（复用总基类通道）、按模块聚合、
 * Web Vitals 按活动模块归属、模块路由作用域（活动模块与渲染耗时）。
 */

import { BaseObject, configureBase, resetBaseSinks } from '@bms/core'
import type { Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  installModuleRouteScope,
  installObservability,
  moduleReporterRegistry,
  moduleSnapshot,
  moduleTelemetry,
  reportModuleError,
  resetModuleTelemetry,
} from '@/observability'
import { createModuleReporterSink } from '@/observability/reporter'
import { activeModule, clearActiveModule, setActiveModule, withModuleScope } from '@/observability/scope'

/** Web Vitals 回调收集（mock 官方库，避免依赖浏览器 PerformanceObserver）。 */
const { vitalsCallbacks } = vi.hoisted(() => ({ vitalsCallbacks: [] as ((metric: unknown) => void)[] }))
vi.mock('web-vitals', () => ({
  onCLS: (callback: (metric: unknown) => void) => {
    vitalsCallbacks.push(callback)
  },
  onINP: (callback: (metric: unknown) => void) => {
    vitalsCallbacks.push(callback)
  },
  onLCP: (callback: (metric: unknown) => void) => {
    vitalsCallbacks.push(callback)
  },
}))

beforeEach(() => {
  resetModuleTelemetry()
  clearActiveModule()
  resetBaseSinks()
  vitalsCallbacks.length = 0
})

afterEach(() => {
  resetBaseSinks()
  clearActiveModule()
})

describe('错误上报与按模块归因（Kiwi 982）', () => {
  it('模块感知 sink：活动模块作用域内补模块名与版本', async () => {
    const sink = createModuleReporterSink(moduleTelemetry)

    await withModuleScope('demo', '0.1.0', async () => {
      sink(new Error('boom'), { scope: 'setup' })
    })

    expect(moduleSnapshot().modules.demo.errors[0]).toMatchObject({
      name: 'demo',
      version: '0.1.0',
      phase: 'setup',
      message: 'boom',
    })
  })

  it('复用总基类上报通道：BaseObject.reportError 经 configureBase sink 归到模块', async () => {
    configureBase({ reporter: createModuleReporterSink(moduleTelemetry) })

    await withModuleScope('demo', '0.1.0', async () => {
      new BaseObject().reportError(new Error('render 失败'), { scope: 'render' })
    })

    expect(moduleSnapshot().modules.demo.errors[0]).toMatchObject({ phase: 'render', message: 'render 失败' })
  })

  it('无活动模块归 platform；显式上报按给定模块与阶段归集', () => {
    const sink = createModuleReporterSink(moduleTelemetry)
    sink(new Error('platform 错'), {})

    reportModuleError('demo', '0.2.0', 'mount', new Error('mount 错'))

    const snapshot = moduleSnapshot()
    expect(snapshot.platform.errors[0]).toMatchObject({ name: 'platform', message: 'platform 错' })
    expect(snapshot.modules.demo.errors[0]).toMatchObject({ name: 'demo', version: '0.2.0', phase: 'mount' })
  })

  it('非 Error 抛出值与空模块名：按字符串归因、空名归 platform（防御分支）', () => {
    const sink = createModuleReporterSink(moduleTelemetry)
    // 非 Error 抛出值 + 非字符串 meta.scope：message 取 String(error)、phase 回落 runtime。
    sink('字符串错误', { scope: 42 })
    // 显式上报空模块名：归 platform。
    reportModuleError('', '0.0.0', 'load', '非 Error')

    const errors = moduleSnapshot().platform.errors
    expect(errors.map((item) => item.message)).toEqual(['字符串错误', '非 Error'])
    expect(errors[0]?.phase).toBe('runtime')
  })
})

describe('Web Vitals 按模块归属（Kiwi 982）', () => {
  it('安装后按回调时刻活动模块归属；非模块路由归 platform', () => {
    installObservability()
    expect(vitalsCallbacks).toHaveLength(3)

    setActiveModule('demo', '0.1.0')
    vitalsCallbacks[0]?.({ name: 'LCP', value: 1234, rating: 'good' })
    clearActiveModule()
    vitalsCallbacks[0]?.({ name: 'LCP', value: 1300, rating: 'good' })

    const snapshot = moduleSnapshot()
    expect(snapshot.modules.demo.vitals[0]).toMatchObject({ metric: 'LCP', value: 1234, rating: 'good' })
    expect(snapshot.platform.vitals[0]).toMatchObject({ metric: 'LCP', value: 1300 })
  })

  it('上报实现解析失败时不注入遥测（防御分支；Vitals 采集仍安装）', () => {
    const registerSpy = vi.spyOn(moduleReporterRegistry, 'register').mockImplementation(() => {})
    const resolveSpy = vi.spyOn(moduleReporterRegistry, 'resolve').mockReturnValueOnce(undefined)
    try {
      installObservability()
    } finally {
      registerSpy.mockRestore()
      resolveSpy.mockRestore()
    }

    expect(vitalsCallbacks).toHaveLength(3)
  })
})

describe('模块路由作用域（Kiwi 982）', () => {
  it('路由就绪更新活动模块并记渲染耗时；平台路由清除活动模块', () => {
    let before: (() => void) | undefined
    let after: ((to: { name: unknown }) => void) | undefined
    const router = {
      beforeEach: (fn: () => void) => {
        before = fn
      },
      afterEach: (fn: (to: { name: unknown }) => void) => {
        after = fn
      },
    } as unknown as Router

    installModuleRouteScope(router, (name) => (name === 'DemoHome' ? { name: 'demo', version: '0.1.0' } : undefined))

    before?.()
    after?.({ name: 'DemoHome' })
    expect(activeModule()).toEqual({ name: 'demo', version: '0.1.0' })
    expect(moduleSnapshot().modules.demo.load.some((item) => item.phase === 'render')).toBe(true)

    after?.({ name: 'HomeView' })
    expect(activeModule()).toBeNull()
  })

  it('未经过导航前置钩子（无导航起点）时只更新活动模块、不记渲染耗时', () => {
    let after: ((to: { name: unknown }) => void) | undefined
    const router = {
      beforeEach: () => {},
      afterEach: (fn: (to: { name: unknown }) => void) => {
        after = fn
      },
    } as unknown as Router

    installModuleRouteScope(router, (name) => (name === 'DemoHome' ? { name: 'demo', version: '0.1.0' } : undefined))
    after?.({ name: 'DemoHome' })

    expect(activeModule()).toEqual({ name: 'demo', version: '0.1.0' })
    expect(moduleSnapshot().modules.demo?.load ?? []).toEqual([])
  })
})

// kiwi_id: 2231（05_03 守卫决策记录：观测面板「守卫决策（平台）」区块数据源）
describe('守卫决策记录（Kiwi 2231）', () => {
  it('守卫记录进入平台组 guards（面板数据源），reset 后清空', () => {
    moduleTelemetry.record({
      kind: 'guard',
      decision: 'login',
      path: '/org/users',
      reason: 'no-session',
      at: '2026-10-02T00:00:00.000Z',
    })
    moduleTelemetry.record({
      kind: 'guard',
      decision: 'allow',
      path: '/',
      reason: 'session-ready',
      at: '2026-10-02T00:00:01.000Z',
    })

    const guards = moduleSnapshot().platform.guards
    expect(guards).toHaveLength(2)
    expect(guards[0]).toMatchObject({ decision: 'login', path: '/org/users', reason: 'no-session' })
    expect(guards[1]).toMatchObject({ decision: 'allow', path: '/', reason: 'session-ready' })

    resetModuleTelemetry()
    expect(moduleSnapshot().platform.guards).toEqual([])
  })
})
