/**
 * 布局组件基类（布局族）：栅格列数 / 间距 / 显隐。
 */

import { BaseSized } from './sized'

/** 布局组件基类（抽象）。 */
export abstract class BaseLayout extends BaseSized {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'layout'
  /** 栅格总列数。 */
  columns = 24
  /** 间距（像素 / 令牌键）。 */
  gap: number | string = 0
  /** 是否隐藏。 */
  hidden = false

  /**
   * 设置显隐。
   *
   * @param hidden 是否隐藏。
   */
  setHidden(hidden: boolean): void {
    this.hidden = hidden
    this.notifyLifecycle('update')
  }
}
