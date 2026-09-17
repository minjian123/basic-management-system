/**
 * 视图解析共享工厂（框架无关核心领域层）：宿主视图解析器的覆盖 / 恢复语义。
 *
 * **未注入 = 未注册**（返回 `null`，调用方回退占位视图），占位保真。
 */

import type { ViewResolver } from '../contracts/view-resolver'

export interface ViewResolverService<TView = unknown> {
  /** 注入视图解析器（传 `undefined` 恢复未注入） */
  configure(next: ViewResolver<TView> | undefined): void
  /** 视图名 → 视图（未注入 / 未注册返回 `null`） */
  resolve(name: string): TView | null
}

export function createViewResolverService<TView = unknown>(): ViewResolverService<TView> {
  let resolver: ViewResolver<TView> | undefined
  return {
    configure(next) {
      resolver = next
    },
    resolve(name) {
      return resolver ? resolver(name) : null
    },
  }
}
