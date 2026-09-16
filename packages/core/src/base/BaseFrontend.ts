/**
 * 根系（框架无关核心）：一切前端基类之根。
 *
 * 纯 TS——不得依赖 Vue / UI 库 / DOM 框架；通用字段（命名空间、版本）与通用方法
 * （日志、错误上报、配置读取、生命周期）的唯一落点。
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface FrontendLogger {
  log(level: LogLevel, message: string, context?: Record<string, unknown>): void
}

/** 缺省日志（无副作用；宿主 / 插件按需注入） */
export const silentLogger: FrontendLogger = {
  log: () => {},
}

export interface FrontendConfigReader {
  get<T>(key: string, fallback?: T): T
}

/** 缺省配置读取（空读取；宿主注入） */
export const emptyConfig: FrontendConfigReader = {
  get: <T,>(_key: string, fallback?: T): T => fallback as T,
}

export interface FrontendBaseOptions {
  /** 命名空间（样式类 / 数据属性前缀；缺省 `bms`） */
  ns?: string
  /** 版本标识（日志 / 上报用） */
  version?: string
  logger?: FrontendLogger
  config?: FrontendConfigReader
  /** 错误上报（缺省仅记录；生产由宿主 / 插件注入监控） */
  errorReporter?: (error: unknown, context?: Record<string, unknown>) => void
}

export class BaseFrontend {
  readonly ns: string
  readonly version: string

  protected readonly logger: FrontendLogger
  protected readonly configReader: FrontendConfigReader
  protected readonly errorReporter: ((error: unknown, context?: Record<string, unknown>) => void) | undefined

  constructor(options: FrontendBaseOptions = {}) {
    this.ns = options.ns ?? 'bms'
    this.version = options.version ?? '0.0.0'
    this.logger = options.logger ?? silentLogger
    this.configReader = options.config ?? emptyConfig
    this.errorReporter = options.errorReporter
  }

  /** 统一日志入口（级别过滤 / 上下文注入由注入的 logger 决定） */
  log(level: LogLevel, message: string, context?: Record<string, unknown>): void {
    this.logger.log(level, `[${this.ns}] ${message}`, context)
  }

  /** 错误上报（先记录，再委托注入的上报器） */
  reportError(error: unknown, context?: Record<string, unknown>): void {
    this.log('error', error instanceof Error ? error.message : String(error), context)
    this.errorReporter?.(error, context)
  }

  /** 配置读取（缺省空读取；宿主注入真实读取实现） */
  getConfig<T>(key: string, fallback?: T): T {
    return this.configReader.get(key, fallback)
  }

  /** 生命周期钩子（子类覆写；幂等由子类保证） */
  dispose(): void {}
}
