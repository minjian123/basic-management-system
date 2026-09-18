/**
 * 尺寸档位能力基类：尺寸 / 密度档位与设计令牌消费的统一入口。
 */

import { BaseComponent, type SizeToken } from '../base/BaseComponent'

/** 尺寸能力基类（抽象）。 */
export abstract class BaseSized extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'sized'

  /** 尺寸语义值（复用组件根档位）。 */
  get sizeToken(): SizeToken {
    return this.size
  }

  /** 是否紧凑密度。 */
  get isCompact(): boolean {
    return this.density === 'compact'
  }
}
