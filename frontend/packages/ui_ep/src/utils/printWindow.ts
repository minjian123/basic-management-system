/** 浏览器打印调用（件层 DOM 语义的唯一落点；打印样式经 `@media print` 生效，核心与投影层不触 DOM）。 */

/**
 * 调起浏览器打印。
 *
 * @returns 是否成功调起（环境不支持时返回 `false`，不抛错）。
 */
export function invokeBrowserPrint(): boolean {
  if (typeof window === 'undefined') {
    return false
  }
  const printer = window.print
  if (typeof printer !== 'function') {
    return false
  }
  printer.call(window)
  return true
}
