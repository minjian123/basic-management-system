/**
 * 确认服务共享工厂（框架无关核心领域层）：覆盖 / 恢复语义统一，默认实现由插件提供。
 *
 * - 未覆盖 → 默认实现（PC 为 `ElMessageBox`、移动端为 Vant `showConfirmDialog`）；
 * - `configure(undefined)` 恢复默认；
 * - 覆盖实现的 rejection 原样传播（取消语义由默认实现自捕获，返回 `false`）。
 */

import type { ConfirmHandler, ConfirmOptions } from '../contracts/confirm'

export interface ConfirmService {
  /** 覆盖确认实现（传 `undefined` 恢复默认） */
  configure(next: ConfirmHandler | undefined): void
  /** 弹确认框（默认实现由创建方提供） */
  confirm(options: ConfirmOptions): Promise<boolean>
}

export function createConfirmService(defaultHandler: ConfirmHandler): ConfirmService {
  let handler: ConfirmHandler | undefined
  return {
    configure(next) {
      handler = next
    },
    confirm(options) {
      return (handler ?? defaultHandler)(options)
    },
  }
}
