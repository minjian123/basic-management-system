/** 水印能力：水印文本生成（用户 / 租户信息注入；绘制由插件承担）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface WatermarkOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 水印分段（缺省：用户名 / 时间由调用方经 `lines` 传入） */
}

export class BaseWatermark extends BaseCapability {
  readonly text = observable('')
  readonly visible = observable(false)

  constructor(options: WatermarkOptions = {}) {
    super({ ...options, key: options.key ?? 'watermark' })
  }

  /** 生成水印文本（多段以 ` · ` 连接；空段忽略） */
  build(lines: readonly (string | undefined)[]): string {
    const text = lines.filter((line) => line && line.length > 0).join(' · ')
    this.text.set(text)
    return text
  }

  show(): void {
    this.visible.set(true)
  }

  hide(): void {
    this.visible.set(false)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), visible: this.visible.get() }
  }
}
