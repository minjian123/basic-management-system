/**
 * 根系组合式：为 `<script setup>` 组件与纯函数式基类提供与 `BaseFrontend` 等价的能力。
 *
 * Vue 3 无类多继承，组合式是「继承」的等价形态（双轨：类继承 / 组合式）；
 * 两轨能力等价，口径见《前端开发规范》「继承与组合分工（强制）」节。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import { BaseFrontend, type FrontendBaseOptions, type FrontendEnv, type LogLevel } from './BaseFrontend'

/** 组合式返回值：与 `BaseFrontend` 的公开成员等价 */
export interface UseFrontendBaseReturn {
  ns: string
  identifier: string
  readonly env: FrontendEnv
  readonly config: Readonly<Record<string, unknown>>
  log: (level: LogLevel, message: string, meta?: Record<string, unknown>) => void
  reportError: (error: unknown, meta?: Record<string, unknown>) => void
  getConfig: <T = unknown>(key: string, fallback?: T) => T
  t: (key: string, params?: Record<string, unknown>) => string
  dispose: () => void
}

/** 作用域实例：承载与根系类完全相同的能力（组合轨不另起炉灶） */
class ScopedFrontendBase extends BaseFrontend {}

/**
 * 获取根系能力（组合轨）。
 *
 * 处于组件 / 副作用作用域内时，随作用域释放自动 `dispose()`；作用域外调用不报错，
 * 可由调用方手动 `dispose()`。
 */
export function useFrontendBase(options: FrontendBaseOptions = {}): UseFrontendBaseReturn {
  const instance = new ScopedFrontendBase(options)
  if (getCurrentScope()) {
    onScopeDispose(() => instance.dispose())
  }
  return {
    ns: instance.ns,
    identifier: instance.identifier,
    get env() {
      return instance.env
    },
    get config() {
      return instance.config
    },
    log: (level, message, meta) => instance.log(level, message, meta),
    reportError: (error, meta) => instance.reportError(error, meta),
    getConfig: (key, fallback) => instance.getConfig(key, fallback),
    t: (key, params) => instance.t(key, params),
    dispose: () => instance.dispose(),
  }
}
