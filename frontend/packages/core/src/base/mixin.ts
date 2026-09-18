/**
 * 混入：把 `BaseObject` 的公共能力（命名空间 / 版本 / 日志 / 上报 / 配置 / 生命周期）注入任意基类。
 *
 * 用于 TS 不支持多重继承的场景——如 `BaseError` 需同时保留 `instanceof Error` 与堆栈、
 * 又取得总基类能力（体系「唯一有理由的多重继承」）。
 */

import { getBaseSinks, type LogLevel } from './BaseObject'

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- 混入构造签名需接受任意实参
type AnyConstructor<T = object> = new (...args: any[]) => T

/** 混入后具备的 `BaseObject` 公共面。 */
export interface BaseObjectSurface {
  readonly namespace: string
  readonly version: string
  readonly isDisposed: boolean
  log(level: LogLevel, message: string, meta?: Record<string, unknown>): void
  reportError(error: unknown, meta?: Record<string, unknown>): void
  getConfig<T>(key: string, fallback?: T): T
  dispose(): void
}

/**
 * 把 `BaseObject` 公共面混入 `Base`。
 *
 * @param Base 目标基类（如 `Error`）。
 * @param namespace 命名空间（缺省 `base`）。
 * @returns 具备 `BaseObject` 公共面的派生类。
 */
export function withBaseObject<TBase extends AnyConstructor>(Base: TBase, namespace = 'base') {
  return class BaseObjectMixed extends Base implements BaseObjectSurface {
    readonly namespace: string = namespace
    readonly version: string = '0.0.0'
    #disposed = false

    get isDisposed(): boolean {
      return this.#disposed
    }

    log(level: LogLevel, message: string, meta?: Record<string, unknown>): void {
      getBaseSinks().logger(level, `[${this.namespace}] ${message}`, meta)
    }

    reportError(error: unknown, meta?: Record<string, unknown>): void {
      getBaseSinks().reporter(error, meta)
    }

    getConfig<T>(key: string, fallback?: T): T {
      const value = getBaseSinks().config.get(key)
      return (value === undefined ? fallback : value) as T
    }

    dispose(): void {
      if (this.#disposed) {
        return
      }
      this.#disposed = true
      this.onDispose()
    }

    protected onDispose(): void {}
  }
}
