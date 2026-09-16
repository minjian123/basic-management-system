/** 布局形态能力：栅格 / 断点 / 间距骨架（令牌读数经 `design-token` 注入），依赖 `design-token`。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export type Breakpoint = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

export interface LayoutOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 当前断点（由渲染插件按视口写入；核心不做 DOM 监听） */
  breakpoint?: Breakpoint
}

export class BaseLayout extends BaseCapability {
  readonly breakpoint = observable<Breakpoint>('md')

  constructor(options: LayoutOptions = {}) {
    super({ ...options, key: options.key ?? 'layout' })
    this.breakpoint.set(options.breakpoint ?? 'md')
  }

  /** 当前断点是否达到（防「移动端优于桌面」类判断散落） */
  atLeast(target: Breakpoint): boolean {
    const order: Breakpoint[] = ['xs', 'sm', 'md', 'lg', 'xl']
    return order.indexOf(this.breakpoint.get()) >= order.indexOf(target)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), breakpoint: this.breakpoint.get() }
  }
}
