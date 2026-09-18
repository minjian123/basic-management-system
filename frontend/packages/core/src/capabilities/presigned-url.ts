/**
 * 预签名能力基类：获取 / 失效重取 / 降级（获取器由宿主注入，占位不请求）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 预签名结果。 */
export interface PresignedResult {
  /** 预签名 URL。 */
  url: string
  /** 过期时间戳（毫秒）。 */
  expiresAt: number
}

/** 预签名能力基类（抽象）。 */
export abstract class BasePresignedUrl extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'presigned-url'
  /** 当前 URL。 */
  url: string | undefined
  /** 过期时间戳（毫秒）。 */
  expiresAt = 0
  /** URL 获取器（未注入则按占位返回已有值）。 */
  fetcher: (() => Promise<PresignedResult>) | undefined

  /** 获取可用 URL（有效则复用，失效重取；未注入获取器则降级返回已有值）。 */
  async get(): Promise<string | undefined> {
    if (this.url !== undefined && !this.isExpired()) {
      return this.url
    }
    if (this.fetcher === undefined) {
      return this.url
    }
    const result = await this.fetcher()
    this.url = result.url
    this.expiresAt = result.expiresAt
    return this.url
  }

  /** 清除缓存（失效重取）。 */
  refresh(): void {
    this.url = undefined
    this.expiresAt = 0
  }

  /**
   * 是否已过期。
   *
   * @param now 当前时间戳（缺省 `Date.now()`）。
   */
  isExpired(now: number = Date.now()): boolean {
    return this.expiresAt > 0 && now >= this.expiresAt
  }
}
