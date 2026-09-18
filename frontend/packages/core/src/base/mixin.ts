/**
 * 混入：把 `BaseObject` 的公共能力（命名空间 / 版本 / 日志 / 上报 / 配置 / 生命周期）注入任意基类。
 *
 * 用于 TS 不支持多重继承的场景——如 `BaseError` 需同时保留 `instanceof Error` 与堆栈、
 * 又取得总基类能力（体系「唯一有理由的多重继承」）。
 */

import { getBaseSinks, type LogLevel } from './BaseObject'

/** 可被混入的构造器类型（接受任意实参）。 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- 混入构造签名需接受任意实参
type AnyConstructor<T = object> = new (...args: any[]) => T

/** 混入后具备的 `BaseObject` 公共面。 */
export interface BaseObjectSurface {
  /** 命名空间（日志前缀 / 错误定位）。 */
  readonly namespace: string
  /** 版本。 */
  readonly version: string
  /** 是否已释放。 */
  readonly isDisposed: boolean
  /** 统一日志。 */
  log(level: LogLevel, message: string, meta?: Record<string, unknown>): void
  /** 统一错误上报。 */
  reportError(error: unknown, meta?: Record<string, unknown>): void
  /** 配置读取（未命中返回 `fallback`）。 */
  getConfig<T>(key: string, fallback?: T): T
  /** 生命周期释放（幂等）。 */
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
    /** 命名空间。 */
    readonly namespace: string = namespace
    /** 版本。 */
    readonly version: string = '0.0.0'
    /** 是否已释放。 */
    #disposed = false

    /** 是否已释放。 */
    get isDisposed(): boolean {
      return this.#disposed
    }

    /** 统一日志。 */
    log(level: LogLevel, message: string, meta?: Record<string, unknown>): void {
      getBaseSinks().logger(level, `[${this.namespace}] ${message}`, meta)
    }

    /** 统一错误上报。 */
    reportError(error: unknown, meta?: Record<string, unknown>): void {
      getBaseSinks().reporter(error, meta)
    }

    /** 配置读取（未命中返回 `fallback`）。 */
    getConfig<T>(key: string, fallback?: T): T {
      const value = getBaseSinks().config.get(key)
      return (value === undefined ? fallback : value) as T
    }

    /** 生命周期释放（幂等；首次调用触发一次 `onDispose`）。 */
    dispose(): void {
      if (this.#disposed) {
        return
      }
      this.#disposed = true
      this.onDispose()
    }

    /** 子类释放钩子（缺省空实现）。 */
    protected onDispose(): void {}
  }
}
