/**
 * 移动端宿主根系装配（S4c 切流）：日志与错误上报出口（sink 可注入，测试用）。
 *
 * 核心 `BaseFrontend` 不含全局 sink 概念；本适配提供宿主统一出口（缺省落控制台），
 * stores / 请求层经 `hostBaseOptions` / `createHostBase` 消费。
 */

import { BaseFrontend, type FrontendBaseOptions, type LogLevel } from '@bms/core'

export interface HostLogRecord {
  ns: string
  identifier: string
  level: LogLevel
  message: string
  meta?: Record<string, unknown>
}

export interface HostErrorRecord {
  ns: string
  identifier: string
  /** 错误名（Error.name；非 Error 时缺省） */
  name?: string
  message: string
  meta?: Record<string, unknown>
}

export interface HostSinks {
  log?: (record: HostLogRecord) => void
  error?: (record: HostErrorRecord) => void
}

let sinks: HostSinks = {}

/** 注入宿主 sink（测试静音 / 采集） */
export function setHostSinks(next: HostSinks): void {
  sinks = next
}

/** 恢复缺省 sink（控制台） */
export function resetHostSinks(): void {
  sinks = {}
}

function emitLog(record: HostLogRecord): void {
  if (sinks.log) {
    sinks.log(record)
    return
  }
  const line = `[${record.ns}:${record.identifier}] ${record.message}`
  if (record.level === 'error') {
    console.error(line)
  } else if (record.level === 'warn') {
    console.warn(line)
  } else {
    console.debug(line)
  }
}

function emitError(record: HostErrorRecord): void {
  if (sinks.error) {
    sinks.error(record)
    return
  }
  console.error(`[${record.ns}:${record.identifier}] ${record.message}`)
}

export interface HostBaseContext {
  ns: string
  identifier: string
}

/** 宿主根系选项：日志 / 错误上报经宿主 sink；其余走核心缺省（静音日志出口由本适配兜底） */
export function hostBaseOptions(context: HostBaseContext): FrontendBaseOptions {
  return {
    ns: context.ns,
    logger: {
      log: (level, message, meta) => {
        const prefix = `[${context.ns}] `
        emitLog({
          ...context,
          level,
          message: message.startsWith(prefix) ? message.slice(prefix.length) : message,
          meta,
        })
      },
    },
    errorReporter: (error, meta) => {
      emitError({
        ...context,
        name: error instanceof Error ? error.name : undefined,
        message: error instanceof Error ? error.message : String(error),
        meta,
      })
    },
  }
}

/** 宿主根系实例（类轨；`BaseApi` 等使用） */
export function createHostBase(
  context: HostBaseContext,
  options: FrontendBaseOptions = {},
): BaseFrontend {
  return new BaseFrontend({ ...hostBaseOptions(context), ...options })
}
