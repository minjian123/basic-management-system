/**
 * 菜单状态共享工厂（框架无关核心领域层）：非受控模式下宿主提供者的覆盖 / 恢复语义。
 *
 * 未注入 = 空菜单（占位保真，对齐旧 store「未注入 loader 置空清单」语义）。
 */

import type { MenuSourceProvider } from '../contracts/menu-source'

export interface MenuSourceService {
  /** 注入菜单状态提供者（传 `undefined` 恢复未注入） */
  configure(next: MenuSourceProvider | undefined): void
  /** 读取菜单状态提供者（未注入返回 `undefined`） */
  get(): MenuSourceProvider | undefined
}

export function createMenuSourceService(): MenuSourceService {
  let provider: MenuSourceProvider | undefined
  return {
    configure(next) {
      provider = next
    },
    get() {
      return provider
    },
  }
}
