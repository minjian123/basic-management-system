/** 防抖工具：定时器统一入口（远程搜索等场景由件层调用，组件不得自行调度定时器）。 */

/** 防抖函数面。 */
export interface DebouncedFunction<T extends unknown[]> {
  /** 调用（等待期内的新调用重置计时）。 */
  (...args: T): void
  /** 取消未触发的调用。 */
  cancel(): void
}

/**
 * 创建防抖函数。
 *
 * @param fn 目标函数。
 * @param wait 等待毫秒数（负数按 0）。
 * @returns 防抖函数（含 `cancel`）。
 */
export function debounce<T extends unknown[]>(fn: (...args: T) => void, wait: number): DebouncedFunction<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const delay = Math.max(0, wait)
  const wrapped = (...args: T): void => {
    if (timer !== undefined) {
      clearTimeout(timer)
    }
    timer = setTimeout(() => {
      timer = undefined
      fn(...args)
    }, delay)
  }
  wrapped.cancel = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
  }
  return wrapped
}
