/**
 * 根系投影（Vue 绑定插件）：核心 `BaseFrontend` ↔ 组合式（宿主 stores / 请求层消费）。
 *
 * 最小 API 面：`log` / `reportError` / `getConfig` / `dispose`；`identifier` 由宿主用于
 * 日志与上报定位（核心类不含该字段，投影原样带回）。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import {
  BaseFrontend,
  type FrontendConfigReader,
  type FrontendLogger,
  type LogLevel,
} from '@bms/core'

export interface UseFrontendBaseOptions {
  /** 命名空间（日志前缀） */
  ns?: string
  /** 实例标识（日志 / 上报定位；投影原样返回） */
  identifier?: string
  version?: string
  logger?: FrontendLogger
  config?: FrontendConfigReader
  /** 错误上报（缺省仅记录；宿主 / 插件注入） */
  errorReporter?: (error: unknown, context?: Record<string, unknown>) => void
}

export interface UseFrontendBaseReturn {
  readonly ns: string
  readonly identifier: string
  readonly version: string
  log(level: LogLevel, message: string, meta?: Record<string, unknown>): void
  reportError(error: unknown, meta?: Record<string, unknown>): void
  getConfig<T = unknown>(key: string, fallback?: T): T
  dispose(): void
}

export function useFrontendBase(options: UseFrontendBaseOptions = {}): UseFrontendBaseReturn {
  const instance = new BaseFrontend({
    ns: options.ns,
    version: options.version,
    logger: options.logger,
    config: options.config,
    errorReporter: options.errorReporter,
  })

  if (getCurrentScope()) {
    onScopeDispose(() => instance.dispose())
  }

  return {
    ns: instance.ns,
    identifier: options.identifier ?? '',
    version: instance.version,
    log: (level, message, meta) => instance.log(level, message, meta),
    reportError: (error, meta) => instance.reportError(error, meta),
    getConfig: (key, fallback) => instance.getConfig(key, fallback),
    dispose: () => instance.dispose(),
  }
}
