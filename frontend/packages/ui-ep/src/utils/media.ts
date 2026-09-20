/** 系统媒体查询（深色偏好 / 减弱动效 / 断点）单一落点：查询与变化订阅。 */

/** 环境是否支持 matchMedia。 */
export function supportsMediaQuery(): boolean {
  return typeof globalThis.matchMedia === 'function'
}

/**
 * 系统是否偏好深色。
 *
 * @returns 是否深色。
 */
export function prefersDark(): boolean {
  return typeof globalThis.matchMedia === 'function'
    ? globalThis.matchMedia('(prefers-color-scheme: dark)').matches
    : false
}

/**
 * 系统是否要求减弱动效。
 *
 * @returns 是否减弱动效。
 */
export function prefersReducedMotion(): boolean {
  return typeof globalThis.matchMedia === 'function'
    ? globalThis.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false
}

/**
 * 订阅媒体查询变化（能力缺失时返回空取消函数，不抛错）。
 *
 * @param query 媒体查询串。
 * @param handler 变化回调（入参为是否命中）。
 * @returns 取消函数。
 */
export function onMediaChange(query: string, handler: (matches: boolean) => void): () => void {
  if (typeof globalThis.matchMedia !== 'function') {
    return () => {}
  }
  const media = globalThis.matchMedia(query)
  const listener = (): void => handler(media.matches)
  media.addEventListener('change', listener)
  return () => media.removeEventListener('change', listener)
}

/**
 * 取媒体查询当前是否命中。
 *
 * @param query 媒体查询串。
 * @returns 是否命中（能力缺失为 `false`）。
 */
export function matchesMedia(query: string): boolean {
  return typeof globalThis.matchMedia === 'function' ? globalThis.matchMedia(query).matches : false
}
