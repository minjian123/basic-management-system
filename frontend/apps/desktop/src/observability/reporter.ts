/**
 * 模块错误上报：把总基类 `BaseObject.reportError` 的调用补模块名与版本后记入遥测。
 *
 * 统一走 `configureBase({ reporter })` 注入的 sink（复用总基类上报通道，不另起通路）；
 * 模块生命周期（加载 / 挂载 / 渲染）错误由宿主显式调用 `reportModuleError` 或经活动模块作用域补全。
 */

import { PLATFORM_MODULE_NAME, type ModuleErrorRecord } from '@bms/core'

import { activeModule } from './scope'

/** 遥测记录入口（避免宿主直接依赖具体遥测器类型）。 */
export interface ErrorRecordSink {
  /**
   * 记一条遥测记录。
   *
   * @param record 记录。
   */
  record(record: ModuleErrorRecord): void
}

/**
 * 构造模块感知的错误上报 sink（`configureBase` 的 reporter）。
 *
 * 活动模块存在时补模块名 / 版本；否则归 `platform`。`meta.scope` 作为失败阶段标注。
 *
 * @param sink 遥测记录入口。
 * @returns 上报 sink。
 */
export function createModuleReporterSink(sink: ErrorRecordSink): (error: unknown, meta?: Record<string, unknown>) => void {
  return (error, meta) => {
    const scope = activeModule()
    sink.record({
      kind: 'error',
      name: scope?.name ?? PLATFORM_MODULE_NAME,
      version: scope?.version ?? '',
      phase: typeof meta?.scope === 'string' ? meta.scope : 'runtime',
      message: error instanceof Error ? error.message : String(error),
      at: new Date().toISOString(),
    })
  }
}

/**
 * 显式上报一条模块错误（加载 / 挂载 / 渲染阶段）。
 *
 * @param sink 遥测记录入口。
 * @param name 模块名。
 * @param version 模块版本。
 * @param phase 失败阶段。
 * @param error 错误。
 */
export function reportModuleError(
  sink: ErrorRecordSink,
  name: string,
  version: string,
  phase: string,
  error: unknown,
): void {
  sink.record({
    kind: 'error',
    name: name === '' ? PLATFORM_MODULE_NAME : name,
    version,
    phase,
    message: error instanceof Error ? error.message : String(error),
    at: new Date().toISOString(),
  })
}
