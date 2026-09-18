/**
 * 模态组件基类（模态族）：模态语义 / 关闭拦截 / 底部操作区。
 */

import { BaseOverlay } from './overlay'

/** 模态组件基类（抽象）。 */
export abstract class BaseModalShell extends BaseOverlay {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'modal-shell'
  /** 点击遮罩是否关闭。 */
  closeOnMask = true
  /** 是否展示底部操作区。 */
  showFooter = true
  /** 关闭前拦截（返回 `false` 阻止关闭）。 */
  beforeClose: (() => boolean) | undefined

  /**
   * 请求关闭（经拦截器；被拦截返回 `false`）。
   *
   * @param reason 关闭原因。
   */
  requestClose(reason = 'close'): boolean {
    if (this.beforeClose !== undefined && !this.beforeClose()) {
      return false
    }
    this.hide(reason)
    return true
  }
}
