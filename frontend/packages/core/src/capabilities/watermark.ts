/**
 * 水印能力基类：用户 / 租户信息注入（覆盖内容与导出）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 水印能力基类（抽象）。 */
export abstract class BaseWatermark extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'watermark'
  /** 是否启用水印。 */
  enabled = true
  /** 用户信息文本。 */
  userText = ''
  /** 租户信息文本。 */
  tenantText = ''

  /** 水印文本（用户 / 租户拼接）。 */
  get text(): string {
    return [this.userText, this.tenantText].filter((part) => part !== '').join(' / ')
  }

  /**
   * 设置用户信息。
   *
   * @param text 用户信息文本。
   */
  setUser(text: string): void {
    this.userText = text
  }

  /**
   * 设置租户信息。
   *
   * @param text 租户信息文本。
   */
  setTenant(text: string): void {
    this.tenantText = text
  }
}
