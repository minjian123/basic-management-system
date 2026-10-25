/** 全屏（Fullscreen API）单一落点：能力判定 / 状态查询 / 进入 / 退出 / 变化订阅（件内不得直触 document 全屏 API）。 */

/**
 * 目标是否支持全屏（缺省根元素）。
 *
 * @param target 目标元素。
 * @returns 是否支持。
 */
export function canFullscreen(target?: Element): boolean {
  if (typeof document === 'undefined') {
    return false
  }
  const element = (target ?? document.documentElement) as HTMLElement
  return typeof element.requestFullscreen === 'function'
}

/**
 * 当前是否处于全屏。
 *
 * @returns 是否全屏。
 */
export function isFullscreen(): boolean {
  return typeof document !== 'undefined' && document.fullscreenElement != null
}

/**
 * 当前全屏元素。
 *
 * @returns 全屏元素（非全屏为 `null`）。
 */
export function fullscreenElement(): Element | null {
  return typeof document !== 'undefined' ? document.fullscreenElement : null
}

/**
 * 进入全屏（缺省根元素；失败时 Promise 拒绝）。
 *
 * @param target 目标元素。
 * @returns 完成 Promise。
 */
export function enterFullscreen(target?: Element): Promise<void> {
  if (typeof document === 'undefined') {
    return Promise.resolve()
  }
  const element = (target ?? document.documentElement) as HTMLElement
  if (typeof element.requestFullscreen !== 'function') {
    return Promise.reject(new Error('fullscreen unsupported'))
  }
  return element.requestFullscreen()
}

/** 退出全屏。 */
export function exitFullscreen(): Promise<void> {
  if (typeof document === 'undefined' || typeof document.exitFullscreen !== 'function') {
    return Promise.resolve()
  }
  return document.exitFullscreen()
}

/**
 * 订阅全屏变化。
 *
 * @param handler 变化回调。
 * @returns 取消函数。
 */
export function onFullscreenChange(handler: () => void): () => void {
  if (typeof document === 'undefined' || typeof document.addEventListener !== 'function') {
    return () => {}
  }
  document.addEventListener('fullscreenchange', handler)
  return () => document.removeEventListener('fullscreenchange', handler)
}
