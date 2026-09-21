/**
 * 上下文能力基类：宿主注入 router / store / i18n / 用户 / 租户（只读约束）。
 *
 * 消费**单一上下文契约**（模块契约的 `ModuleHostContext`）——模块与宿主同一形状，避免两处定义漂移。
 */

import { BaseComponent } from '../base/BaseComponent'

import type { ModuleHostContext } from '../module/types'

/** 上下文键。 */
export type ModuleContextKey = keyof ModuleHostContext

/** 上下文能力基类（抽象）。 */
export abstract class BaseModuleContext extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'module-context'
  /** 只读上下文快照。 */
  #context: Readonly<ModuleHostContext> = Object.freeze({})

  /** 上下文快照（只读）。 */
  get snapshot(): Readonly<ModuleHostContext> {
    return this.#context
  }

  /**
   * 注入上下文（冻结为只读快照；缺省空）。
   *
   * @param context 宿主上下文。
   */
  inject(context: ModuleHostContext = {}): void {
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
