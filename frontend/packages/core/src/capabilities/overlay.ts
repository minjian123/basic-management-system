/**
 * 浮层能力基类：遮罩 / 挂载点 / 层级 / 焦点陷阱 / 关闭语义。
 */

import { BaseSized } from './sized'

/** 浮层开关监听器。 */
export type OverlayListener = (open: boolean, reason: string) => void

/** 浮层能力基类（抽象）。 */
export abstract class BaseOverlay extends BaseSized {
  /** 能力键。 */
  override readonly identifier: string = 'overlay'
  /** 依赖能力键。 */
  override readonly depends = ['sized']
  /** 是否打开。 */
  open = false
  /** 层级。 */
  zIndex = 1000
  /** 挂载目标选择器（缺省宿主根）。 */
  mountTarget: string | null = null
  /** 是否焦点陷阱。 */
  focusTrap = true
  /** 开关监听器。 */
  #listeners = new Set<OverlayListener>()

  /** 打开浮层。 */
  show(): void {
    this.#toggle(true, 'show')
  }

  /**
   * 关闭浮层。
   *
   * @param reason 关闭原因。
   */
  hide(reason = 'close'): void {
    this.#toggle(false, reason)
  }

  /**
   * 订阅开关变化。
   *
   * @param listener 监听器。
   * @returns 取消函数（幂等）。
   */
  onToggle(listener: OverlayListener): () => void {
    this.#listeners.add(listener)
    return () => {
      this.#listeners.delete(listener)
    }
  }

  /** 切换开关并广播（同态不触发）。 */
  #toggle(open: boolean, reason: string): void {
    if (open === this.open) {
      return
    }
    this.open = open
    for (const listener of [...this.#listeners]) {
      try {
        listener(open, reason)
      } catch (error) {
        this.reportError(error, { scope: 'BaseOverlay.onToggle' })
      }
    }
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
