/**
 * 容器组件基类（容器族）：折叠 / 分栏 / 区域令牌。
 */

import { BaseSized } from './sized'

/** 容器组件基类（抽象）。 */
export abstract class BaseContainer extends BaseSized {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'container'
  /** 是否可折叠。 */
  collapsible = false
  /** 是否已折叠。 */
  collapsed = false
  /** 是否分栏。 */
  split = false

  /** 切换折叠（仅当可折叠）。 */
  toggleCollapse(): void {
    if (!this.collapsible) {
      return
    }
    this.collapsed = !this.collapsed
    this.notifyLifecycle('update')
  }
}
