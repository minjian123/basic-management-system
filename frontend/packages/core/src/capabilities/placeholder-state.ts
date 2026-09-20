/**
 * 占位状态能力基类：依赖后端数据的件在数据通路未就绪时的降级语义
 * （就绪 / 降级、占位零请求计数、状态切换）。
 *
 * 真实实现只换数据通路、不改对外降级语义；**占位态不发起请求、不写缓存、无副作用**。
 * 占位降级为横切功能，公共字段与方法只在链上本基类维护，件内与组合式不得重复实现；
 * **供下位组件基类（`BaseValue` / `BaseDataState` / `BaseNotice` 等）复用，不直接面向具体组件**。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 占位状态能力基类（抽象）。 */
export abstract class BasePlaceholderState extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'placeholder-state'
  /** 数据通路是否就绪（缺省视为就绪；依赖后端的件装配时置 `false`）。 */
  ready = true
  /** 已发起加载次数（占位态必须保持 0）。 */
  requestCount = 0

  /** 是否降级（占位）态（未就绪即降级）。 */
  get degraded(): boolean {
    return !this.ready
  }

  /**
   * 切换就绪态。
   *
   * @param value 是否就绪。
   */
  setReady(value: boolean): void {
    if (this.ready === value) {
      return
    }
    this.ready = value
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /** 标记一次加载（仅就绪后计数，防占位期误计）。 */
  markLoaded(): void {
    if (!this.ready) {
      return
    }
    this.requestCount += 1
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /** 重置请求计数（测试 / 重新就绪用）。 */
  resetRequestCount(): void {
    this.requestCount = 0
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
