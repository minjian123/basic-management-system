/** 全局键盘（window keydown）与指针拖拽（window pointermove / pointerup）单一落点。 */

/**
 * 订阅全局键盘按下。
 *
 * @param handler 键盘回调。
 * @returns 取消函数。
 */
export function onGlobalKeydown(handler: (event: KeyboardEvent) => void): () => void {
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
    return () => {}
  }
  window.addEventListener('keydown', handler)
  return () => window.removeEventListener('keydown', handler)
}

/**
 * 开始指针拖拽（监听 window 的 pointermove / pointerup，松开时自动解绑）。
 *
 * @param onMove 移动回调。
 * @param onEnd 结束回调（可选）。
 * @returns 主动取消函数。
 */
export function startPointerDrag(
  onMove: (event: PointerEvent) => void,
  onEnd?: (event: PointerEvent) => void,
): () => void {
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
    return () => {}
  }
  const move = (event: PointerEvent): void => onMove(event)
  const up = (event: PointerEvent): void => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    onEnd?.(event)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
  return () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
}
