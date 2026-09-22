/**
 * 宿主观测装配（见任务 03_03 详细设计 §3.4 / §3.5）。
 *
 * 创建遥测器单例 + 注册缺省内存上报实现 → 经 `configureBase` 注入**模块感知**上报 sink
 * （复用总基类错误上报通道）→ 安装 Web Vitals 采集（按活动模块归属）；
 * 另提供模块路由作用域安装（路由就绪时更新活动模块并记渲染耗时）。
 */

import {
  InMemoryModuleReporter,
  ModuleReporterProvider,
  ModuleReporterRegistry,
  ModuleTelemetry,
  configureBase,
  type ModuleVitalRecord,
} from '@bms/core'
import type { Router } from 'vue-router'

import { createModuleReporterSink, reportModuleError as recordModuleError } from './reporter'
import { activeModule, clearActiveModule, setActiveModule } from './scope'
import { installWebVitals } from './webVitals'

/** 模块遥测器单例（内存记录 + 按模块聚合）。 */
export const moduleTelemetry = new ModuleTelemetry()

/** 模块上报实现注册表（缺省注册内存实现；真实后端通道后续登记）。 */
export const moduleReporterRegistry = new ModuleReporterRegistry()

/**
 * 安装观测：注册缺省上报实现、注入模块感知上报 sink、安装 Web Vitals 采集。
 */
export function installObservability(): void {
  moduleReporterRegistry.register(new ModuleReporterProvider('memory', () => new InMemoryModuleReporter()))
  const reporter = moduleReporterRegistry.resolve('memory')
  if (reporter !== undefined) {
    moduleTelemetry.useReporter(reporter)
  }
  configureBase({ reporter: createModuleReporterSink(moduleTelemetry) })

  installWebVitals((metric) => {
    const info = activeModule()
    moduleTelemetry.record({
      kind: 'vital',
      name: info?.name ?? null,
      version: info?.version ?? null,
      metric: metric.name as ModuleVitalRecord['metric'],
      value: metric.value,
      rating: metric.rating,
      at: new Date().toISOString(),
    })
  })
}

/**
 * 显式上报模块生命周期错误（加载 / 挂载 / 渲染）。
 *
 * @param name 模块名。
 * @param version 模块版本。
 * @param phase 失败阶段。
 * @param error 错误。
 */
export function reportModuleError(name: string, version: string, phase: string, error: unknown): void {
  recordModuleError(moduleTelemetry, name, version, phase, error)
}

/** 遥测快照（按模块聚合）。 */
export function moduleSnapshot(): ReturnType<ModuleTelemetry['snapshot']> {
  return moduleTelemetry.snapshot()
}

/** 清空遥测记录。 */
export function resetModuleTelemetry(): void {
  moduleTelemetry.reset()
}

/**
 * 安装模块路由作用域：路由就绪时更新活动模块（模块路由）或清除（平台路由），并记渲染耗时。
 *
 * @param router 路由实例。
 * @param resolveModule 路由名 → 模块解析（由宿主按已挂载模块路由提供）。
 */
export function installModuleRouteScope(
  router: Router,
  resolveModule: (routeName: unknown) => { name: string; version: string } | undefined,
): void {
  let navigationStart = 0
  router.beforeEach(() => {
    navigationStart = Date.now()
  })
  router.afterEach((to) => {
    const info = resolveModule(to.name)
    if (info === undefined) {
      clearActiveModule()
      return
    }
    setActiveModule(info.name, info.version)
    if (navigationStart > 0) {
      moduleTelemetry.record({
        kind: 'load',
        name: info.name,
        version: info.version,
        phase: 'render',
        durationMs: Date.now() - navigationStart,
        ok: true,
        at: new Date().toISOString(),
      })
    }
  })
}
