/** 设计令牌 CSS 变量读取单一落点（件内不得直接 getComputedStyle）。 */

/**
 * 读取根元素（或指定元素）上的 CSS 变量值。
 *
 * @param name 变量名（含 `--` 前缀）。
 * @param target 目标元素（缺省根元素）。
 * @returns 变量值（未设置或不可用为 `undefined`）。
 */
export function readCssVar(name: string, target?: Element): string | undefined {
  if (typeof document === 'undefined' || typeof globalThis.getComputedStyle !== 'function') {
    return undefined
  }
  const element = target ?? document.documentElement
  const value = globalThis.getComputedStyle(element).getPropertyValue(name).trim()
  return value === '' ? undefined : value
}
