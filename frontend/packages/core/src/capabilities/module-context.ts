/**
 * 上下文能力基类：宿主注入 router / store / i18n / 用户 / 租户（只读约束）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 宿主注入上下文。 */
export interface ModuleContext {
  /** 路由。 */
  router?: unknown
  /** 状态管理。 */
  store?: unknown
  /** 国际化。 */
  i18n?: unknown
  /** 当前用户。 */
  user?: unknown
  /** 当前租户。 */
  tenant?: unknown
}

/** 上下文键。 */
export type ModuleContextKey = keyof ModuleContext

/** 上下文能力基类（抽象）。 */
export abstract class BaseModuleContext extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'module-context'
  /** 只读上下文快照。 */
  #context: Readonly<ModuleContext> = Object.freeze({})

  /** 上下文快照（只读）。 */
  get snapshot(): Readonly<ModuleContext> {
    return this.#context
  }

  /**
   * 注入上下文（冻结为只读）。
   *
   * @param context 宿主上下文。
   */
  inject(context: ModuleContext): void {
    this.#context = Object.freeze({ ...context })
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 是否已注入某上下文项。
   *
   * @param key 上下文键。
   */
  has(key: ModuleContextKey): boolean {
    return this.#context[key] !== undefined
  }

  /**
   * 读取上下文项。
   *
   * @param key 上下文键。
   */
  get<T = unknown>(key: ModuleContextKey): T | undefined {
    return this.#context[key] as T | undefined
  }
}
