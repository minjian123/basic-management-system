/**
 * 媒体组件基类（媒体族）：加载状态机 / 宽高比 / 过期重取 / 回退。
 */

import { BaseSized } from './sized'

/** 媒体加载状态。 */
export type MediaState = 'loading' | 'ready' | 'error'

/** 媒体组件基类（抽象）。 */
export abstract class BaseMediaContent extends BaseSized {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'media-content'
  /** 加载状态。 */
  state: MediaState = 'loading'
  /** 资源地址。 */
  src = ''
  /** 宽高比（宽 / 高）。 */
  aspectRatio: number | undefined

  /**
   * 设置资源地址（重置为加载中）。
   *
   * @param src 资源地址。
   */
  setSrc(src: string): void {
    this.src = src
    this.state = 'loading'
  }

  /** 标记加载完成。 */
  markReady(): void {
    this.state = 'ready'
  }

  /** 标记加载失败（回退由渲染层按占位呈现）。 */
  markError(): void {
    this.state = 'error'
  }
}
