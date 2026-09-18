/**
 * 订阅基类（对齐后端订阅口径）：把取消函数登记为异步资源，释放时自动取消。
 *
 * `topic` 点分小写、与后端事件域同源；来源解耦（占位总线 / 本地 / 实时）。
 */

import { BaseAsyncResource } from './resource'

/** 订阅基类（抽象）。 */
export abstract class BaseSubscription extends BaseAsyncResource {
  /**
   * 登记取消函数（随资源释放自动调用）。
   *
   * @param unsubscribe 取消函数。
   */
  protected registerUnsubscribe(unsubscribe: () => void): void {
    this.registerDisposable({ dispose: unsubscribe })
  }
}
