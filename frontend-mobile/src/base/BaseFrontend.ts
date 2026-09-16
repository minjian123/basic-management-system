/**
 * 前端根系基类：一切前端基类之根（通用字段 + 通用方法）。
 *
 * 只放「所有基类共有」的横切能力——命名空间、实例标识、运行环境、只读配置视图、
 * 日志、错误上报、配置读取、i18n 取词与生命周期钩子；不含 UI、store 与业务语义。
 * 依赖方向单向：本文件不得引用上层基类、组件与业务模块。
 */

import { i18n } from '@/i18n'

/** 运行环境 */
export type FrontendEnv = 'dev' | 'test' | 'prod'

/** 日志级别（由低到高） */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

/** 根系构造参数 */
export interface FrontendBaseOptions {
  /** 命名空间（日志前缀 / 样式前缀 / 埋点域），默认 `bms` */
  ns?: string
  /** 实例标识（日志与错误上报定位），默认取 `ns` */
  identifier?: string
}

/** 日志记录（注入 sink 的入参） */
export interface LogRecord {
  level: LogLevel
  ns: string
  identifier: string
  message: string
  meta?: Record<string, unknown>
  /** 自上次输出以来的同指纹触发次数（首次为 1） */
  repeat: number
  /** ISO 时间戳 */
  timestamp: string
}

/** 错误上报记录（注入 sink 的入参） */
export interface ErrorRecord {
  ns: string
  identifier: string
  name: string
  message: string
  stack?: string
  meta?: Record<string, unknown>
  /** 自上次输出以来的同指纹触发次数（首次为 1） */
  repeat: number
  /** ISO 时间戳 */
  timestamp: string
}

export type LogSink = (record: LogRecord) => void
export type ErrorSink = (record: ErrorRecord) => void

/** 运行期配置（构建期默认 + 运行期覆盖） */
export interface FrontendRuntimeConfig {
  env: FrontendEnv
  logLevel: LogLevel
  /** 扁平配置键值（构建期 `VITE_*` 解析结果 + 运行期注入） */
  values: Record<string, unknown>
  /** 日志与错误上报的去重限流窗口（毫秒） */
  windowMs: number
}

/** 运行期配置覆盖（浅合并） */
export type FrontendConfigPatch = Partial<FrontendRuntimeConfig>

const DEFAULT_NS = 'bms'
const DEFAULT_WINDOW_MS = 5000
const LEVEL_RANK: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 }

/** 构建期变量视图（Vite 注入；测试环境同样存在） */
const buildEnv = import.meta.env as unknown as Record<string, unknown>

function normalizeEnv(raw: unknown): FrontendEnv {
  if (raw === 'dev' || raw === 'test' || raw === 'prod') {
    return raw
  }
  return buildEnv.PROD === true ? 'prod' : 'dev'
}

/** `VITE_API_BASE` → `api-base`（去前缀、小写、下划线转短横线） */
function normalizeConfigKey(key: string): string {
  return key
    .replace(/^VITE_/, '')
    .replace(/_/g, '-')
    .toLowerCase()
}

/** 构建期解析：`VITE_APP_ENV` 定环境，其余 `VITE_*` 转扁平配置键 */
export function resolveBuildConfig(): FrontendRuntimeConfig {
  const values: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(buildEnv)) {
    if (!key.startsWith('VITE_') || key === 'VITE_APP_ENV') {
      continue
    }
    values[normalizeConfigKey(key)] = value
  }
  const env = normalizeEnv(buildEnv.VITE_APP_ENV)
  return { env, logLevel: env === 'prod' ? 'warn' : 'debug', values, windowMs: DEFAULT_WINDOW_MS }
}

let runtimeConfig: FrontendRuntimeConfig = resolveBuildConfig()
let logSink: LogSink | undefined
let errorSink: ErrorSink | undefined

/** 指纹去重限流状态：窗口起点 + 窗口内触发次数 */
interface FingerprintState {
  firstAt: number
  repeat: number
}

const fingerprints = new Map<string, FingerprintState>()

/**
 * 运行期覆盖运行期配置（浅合并，幂等）。
 *
 * 后端「系统参数」就绪后由应用启动流程调用（阶段六/八回补）；根系接口不变。
 */
export function configureFrontendBase(patch: FrontendConfigPatch): void {
  runtimeConfig = {
    ...runtimeConfig,
    ...patch,
    values: patch.values ? { ...runtimeConfig.values, ...patch.values } : runtimeConfig.values,
  }
}

/** 复位为构建期默认（测试与热重载用；同时清空限流状态） */
export function resetFrontendBaseConfig(): void {
  runtimeConfig = resolveBuildConfig()
  fingerprints.clear()
}

/** 只读运行期配置视图 */
export function getFrontendRuntimeConfig(): Readonly<FrontendRuntimeConfig> {
  return runtimeConfig
}

/**
 * 注入日志 / 错误 sink（不传则回退 console）。
 *
 * 后端上报链路（阶段八/十三）就绪后由此注入，根系不改。
 */
export function setFrontendSinks(sinks: { log?: LogSink; error?: ErrorSink }): void {
  if ('log' in sinks) {
    logSink = sinks.log
  }
  if ('error' in sinks) {
    errorSink = sinks.error
  }
}

/**
 * 指纹去重限流：窗口内同指纹只输出一次；窗口过期后再次出现时，
 * 以「上一窗口累计次数 + 本次」作为 `repeat` 输出一条汇总记录。
 */
function shouldEmit(fingerprint: string, now: number): number | undefined {
  const state = fingerprints.get(fingerprint)
  if (!state) {
    fingerprints.set(fingerprint, { firstAt: now, repeat: 1 })
    return 1
  }
  if (now - state.firstAt < runtimeConfig.windowMs) {
    state.repeat += 1
    return undefined
  }
  const repeat = state.repeat + 1
  fingerprints.set(fingerprint, { firstAt: now, repeat: 1 })
  return repeat
}

/** 按命名空间解析配置视图：全局键 + `${ns}.` 前缀键去除前缀后覆盖 */
function resolveConfigView(ns: string): Readonly<Record<string, unknown>> {
  const prefix = `${ns}.`
  const view: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(runtimeConfig.values)) {
    if (!key.startsWith(prefix)) {
      view[key] = value
    }
  }
  for (const [key, value] of Object.entries(runtimeConfig.values)) {
    if (key.startsWith(prefix)) {
      view[key.slice(prefix.length)] = value
    }
  }
  return Object.freeze(view)
}

/** 错误归一化：Error / string / 其它均可入参，且不抛错 */
interface NormalizedError {
  name: string
  message: string
  stack?: string
}

function normalizeError(error: unknown): NormalizedError {
  if (error instanceof Error) {
    return error.stack
      ? { name: error.name, message: error.message, stack: error.stack }
      : { name: error.name, message: error.message }
  }
  if (typeof error === 'string') {
    return { name: 'Error', message: error }
  }
  try {
    return { name: 'Error', message: JSON.stringify(error) ?? String(error) }
  } catch {
    // 循环引用等无法序列化的入参：退化为字符串描述
    return { name: 'Error', message: String(error) }
  }
}

/** console 降级输出（按级别取当前 console 方法，便于测试桩接） */
function writeConsole(level: LogLevel, ...args: unknown[]): void {
  if (level === 'debug') {
    console.debug(...args)
  } else if (level === 'info') {
    console.info(...args)
  } else if (level === 'warn') {
    console.warn(...args)
  } else {
    console.error(...args)
  }
}

function emitLog(record: LogRecord): void {
  if (logSink) {
    try {
      logSink(record)
      return
    } catch {
      // sink 自身异常不得影响调用方：降级 console 输出
    }
  }
  writeConsole(record.level, `[${record.ns}]`, record.message, record.meta ?? '')
}

function emitError(record: ErrorRecord): void {
  if (errorSink) {
    try {
      errorSink(record)
      return
    } catch {
      // 同上：上报失败不阻断业务
    }
  }
  writeConsole('error', `[${record.ns}]`, record.message, record.stack ?? '')
}

/**
 * 根系基类：一切前端基类的公共父。
 *
 * 子类经 `extends BaseFrontend` 继承（身份轨）；`<script setup>` 组件与纯函数式基类
 * 经 `useFrontendBase()` 获得等价能力（组合轨，见 `useFrontendBase.ts`）。
 */
export abstract class BaseFrontend {
  /** 命名空间（日志前缀 / 样式前缀 / 埋点域） */
  readonly ns: string
  /** 实例标识（日志与错误上报定位） */
  readonly identifier: string

  private disposed = false

  constructor(options: FrontendBaseOptions = {}) {
    this.ns = options.ns?.trim() || DEFAULT_NS
    this.identifier = options.identifier?.trim() || this.ns
    this.onBaseCreated()
  }

  /** 运行环境（实时读运行期配置，构造后 `configureFrontendBase` 同样生效） */
  get env(): FrontendEnv {
    return runtimeConfig.env
  }

  /** 只读配置视图（按命名空间解析：`${ns}.${key}` 覆盖同名全局键） */
  get config(): Readonly<Record<string, unknown>> {
    return resolveConfigView(this.ns)
  }

  /** 统一日志：分级过滤 → 指纹去重限流 → sink（默认 console 分级输出） */
  log(level: LogLevel, message: string, meta?: Record<string, unknown>): void {
    if (LEVEL_RANK[level] < LEVEL_RANK[runtimeConfig.logLevel]) {
      return
    }
    const repeat = shouldEmit(`log|${this.ns}|${level}|${message}`, Date.now())
    if (repeat === undefined) {
      return
    }
    emitLog({
      level,
      ns: this.ns,
      identifier: this.identifier,
      message,
      ...(meta ? { meta } : {}),
      repeat,
      timestamp: new Date().toISOString(),
    })
  }

  /** 统一错误上报：归一化 → 去重限流 → sink；任何入参都不抛错、不阻断业务 */
  reportError(error: unknown, meta?: Record<string, unknown>): void {
    const normalized = normalizeError(error)
    const repeat = shouldEmit(
      `error|${this.ns}|${normalized.name}|${normalized.message}|${normalized.stack ?? ''}`,
      Date.now(),
    )
    if (repeat === undefined) {
      return
    }
    emitError({
      ns: this.ns,
      identifier: this.identifier,
      ...normalized,
      ...(meta ? { meta } : {}),
      repeat,
      timestamp: new Date().toISOString(),
    })
  }

  /** 配置 / 环境读取（含默认值；缺失返回 fallback，不抛错） */
  getConfig<T = unknown>(key: string, fallback?: T): T {
    const value = resolveConfigView(this.ns)[key]
    return (value === undefined ? fallback : value) as T
  }

  /** i18n 取词（委托 vue-i18n；未就绪或缺词回退 key 原文） */
  t(key: string, params?: Record<string, unknown>): string {
    try {
      const result = params ? i18n.global.t(key, params) : i18n.global.t(key)
      return typeof result === 'string' ? result : key
    } catch {
      return key
    }
  }

  /** 幂等释放：触发 `onBaseDisposed`（重复调用无副作用） */
  dispose(): void {
    if (this.disposed) {
      return
    }
    this.disposed = true
    this.onBaseDisposed()
  }

  /** 生命周期钩子：构造完成后触发（供子类扩展） */
  protected onBaseCreated(): void {}

  /** 生命周期钩子：释放时触发（供子类扩展） */
  protected onBaseDisposed(): void {}
}
