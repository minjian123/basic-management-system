/** 模块令牌的 DOM 应用器（宿主）：把令牌写为根元素自定义属性（核心不触 DOM）。 */

import type { ThemeTokenTarget } from '@bms/core'

/**
 * 创建根元素令牌应用器（每次调用即时取根元素，避免早于 DOM 就绪时缓存失效）。
 *
 * @returns 令牌写回目标。
 */
export function documentThemeTarget(): ThemeTokenTarget {
  const style = (): CSSStyleDeclaration | undefined => globalThis.document?.documentElement.style
  return {
    setToken: (name, value) => {
      style()?.setProperty(name, value)
    },
    removeToken: (name) => {
      style()?.removeProperty(name)
    },
  }
}
