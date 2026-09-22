// kiwi_id: 982
/** 模块遥测器与上报实现用例（记录 / 按模块聚合 / 可替换上报 / 环形上限）。 */

import { describe, expect, it } from 'vitest'

import {
  BaseModuleReporter,
  InMemoryModuleReporter,
  ModuleReporterProvider,
  ModuleReporterRegistry,
  ModuleTelemetry,
  type ModuleTelemetryRecord,
} from '../src'

const at = '2026-09-22T00:00:00.000Z'

describe('ModuleTelemetry（Kiwi 982）', () => {
  it('记录并按模块聚合：加载 / 错误 / Vitals；平台项归 platform', () => {
    const telemetry = new ModuleTelemetry()
    telemetry.record({ kind: 'load', name: 'demo', version: '0.1.0', phase: 'resolve', durationMs: 3, ok: true, at })
    telemetry.record({ kind: 'error', name: 'demo', version: '0.1.0', phase: 'setup', message: 'x', at })
    telemetry.record({ kind: 'vital', name: 'demo', version: '0.1.0', metric: 'LCP', value: 1234, rating: 'good', at })
    telemetry.record({ kind: 'error', name: 'platform', version: '', phase: 'load', message: 'y', at })
    telemetry.record({ kind: 'vital', name: null, version: null, metric: 'CLS', value: 0.01, rating: 'good', at })

    const snapshot = telemetry.snapshot()
    expect(snapshot.modules.demo.version).toBe('0.1.0')
    expect(snapshot.modules.demo.load).toHaveLength(1)
    expect(snapshot.modules.demo.errors).toHaveLength(1)
    expect(snapshot.modules.demo.vitals).toHaveLength(1)
    expect(snapshot.platform.errors).toHaveLength(1)
    expect(snapshot.platform.vitals).toHaveLength(1)

    telemetry.reset()
    expect(telemetry.snapshot().modules).toEqual({})
    expect(telemetry.snapshot().platform).toEqual({ errors: [], vitals: [] })
  })

  it('记录转发给可替换上报实现', () => {
    const reporter = new InMemoryModuleReporter()
    const telemetry = new ModuleTelemetry({ reporter })
    const record: ModuleTelemetryRecord = {
      kind: 'error',
      name: 'demo',
      version: '0.1.0',
      phase: 'render',
      message: 'x',
      at,
    }

    telemetry.record(record)

    expect(reporter.records()).toEqual([record])
    reporter.clear()
    expect(reporter.records()).toEqual([])
  })

  it('上报实现注册表：同键拒重、按名 / 缺省解析、未登记返回 undefined', () => {
    const registry = new ModuleReporterRegistry()
    expect(registry.resolve()).toBeUndefined()

    registry.register(new ModuleReporterProvider('memory', () => new InMemoryModuleReporter()))
    expect(registry.resolve()).toBeInstanceOf(InMemoryModuleReporter)
    expect(registry.resolve('memory')).toBeInstanceOf(InMemoryModuleReporter)
    expect(registry.resolve('missing')).toBeUndefined()
    expect(() => registry.register(new ModuleReporterProvider('memory', () => new InMemoryModuleReporter()))).toThrow()

    class CustomReporter extends BaseModuleReporter {
      readonly pluginName = 'custom'
      report(): void {}
    }
    registry.register(new ModuleReporterProvider('custom', () => new CustomReporter()))
    expect(registry.resolve('custom')).toBeInstanceOf(CustomReporter)
  })

  it('环形上限：超出丢最旧', () => {
    const telemetry = new ModuleTelemetry({ capacity: 2 })
    for (let index = 0; index < 3; index += 1) {
      telemetry.record({ kind: 'load', name: 'demo', version: '0.1.0', phase: 'mount', durationMs: index, ok: true, at })
    }

    expect(telemetry.snapshot().modules.demo.load.map((item) => item.durationMs)).toEqual([1, 2])
  })
})
