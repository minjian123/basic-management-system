/** 页面可见性（Page Visibility API）单一落点：状态查询与变化订阅。 */

/**
 * 页面当前是否隐藏。
 *
 * @returns 是否隐藏。
 */
export function isDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden'
}

/**
 * 订阅页面可见性变化（返回当前是否可见）。
 *
 * @param handler 变化回调（入参为是否可见）。
 * @returns 取消函数。
 */
export function onVisibilityChange(handler: (visible: boolean) => void): () => void {
  if (typeof document === 'undefined' || typeof document.addEventListener !== 'function') {
    return () => {}
  }
  const listener = (): void => handler(document.visibilityState !== 'hidden')
  document.addEventListener('visibilitychange', listener)
  return () => document.removeEventListener('visibilitychange', listener)
}
