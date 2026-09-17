/**
 * 异步资源基类（框架无关核心）：登记 / 逆序释放 / 幂等 / 释放后拒绝登记。
 *
 * 与渲染框架解耦：释放时机由宿主 / 渲染插件调用（如组件卸载钩子），核心不做框架绑定。
 */

import { BaseComponent, type ComponentBaseOptions } from '../base/BaseComponent'
import { BaseError, ErrorCodes } from './error'

export type ResourceDisposer = () => void

export class BaseAsyncResource extends BaseComponent {
  private disposers: ResourceDisposer[] = []
  private disposed = false

  constructor(options: ComponentBaseOptions = {}) {
    super(options)
  }

  /** 登记释放函数（释放后拒绝登记） */
  registerResource(disposer: ResourceDisposer): ResourceDisposer {
    if (this.disposed) {
      throw new BaseError(ErrorCodes.NOT_IMPLEMENTED, `资源已释放，拒绝登记（${this.ns}）`)
    }
    this.disposers.push(disposer)
    return disposer
  }

  /** 释放（逆序；幂等） */
  dispose(): void {
    if (this.disposed) {
      return
    }
    for (const disposer of [...this.disposers].reverse()) {
      try {
        disposer()
      } catch (error) {
        this.reportError(error, { phase: 'resource-dispose' })
      }
    }
    this.disposers = []
    this.disposed = true
  }

  get isDisposed(): boolean {
    return this.disposed
  }
}
