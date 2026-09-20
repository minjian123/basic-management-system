/** 元素与窗口观察（IntersectionObserver / ResizeObserver / window resize）单一落点。 */

/** 环境是否支持 IntersectionObserver。 */
export function supportsIntersection(): boolean {
  return typeof IntersectionObserver !== 'undefined'
}

/** 环境是否支持 ResizeObserver。 */
export function supportsResize(): boolean {
  return typeof ResizeObserver !== 'undefined'
}

/**
 * 观察元素进入视口（能力缺失时返回空取消函数，不抛错）。
 *
 * @param target 目标元素。
 * @param handler 命中回调。
 * @param options 观察选项。
 * @returns 取消函数。
 */
export function observeIntersection(
  target: Element,
  handler: (entry: IntersectionObserverEntry) => void,
  options?: IntersectionObserverInit,
): () => void {
  if (typeof IntersectionObserver === 'undefined') {
    return () => {}
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      handler(entry)
    }
  }, options)
  observer.observe(target)
  return () => observer.disconnect()
}

/**
 * 观察元素尺寸变化（能力缺失时返回空取消函数，不抛错）。
 *
 * @param target 目标元素。
 * @param handler 尺寸变化回调。
 * @returns 取消函数。
 */
export function observeResize(target: Element, handler: (entry: ResizeObserverEntry) => void): () => void {
  if (typeof ResizeObserver === 'undefined') {
    return () => {}
  }
  const observer = new ResizeObserver((entries) => {
    for (const entry of entries) {
      handler(entry)
    }
  })
  observer.observe(target)
  return () => observer.disconnect()
}

/**
 * 订阅窗口尺寸变化。
 *
 * @param handler 变化回调。
 * @returns 取消函数。
 */
export function onWindowResize(handler: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
    return () => {}
  }
  window.addEventListener('resize', handler)
  return () => window.removeEventListener('resize', handler)
}

/**
 * 取视口宽度。
 *
 * @returns 视口宽度（非浏览器为 0）。
 */
export function viewportWidth(): number {
  return typeof window !== 'undefined' ? window.innerWidth : 0
}
