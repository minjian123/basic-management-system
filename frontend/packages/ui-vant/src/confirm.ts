/**
 * ui-vant 确认对话框注入点（宿主可覆盖；默认 Vant `showConfirmDialog` 实现）。
 *
 * 契约与覆盖 / 恢复语义单份在 `@bms/core`（`createConfirmService`）；移动端交互按 Vant
 * 对话框语义：取消 / 关闭返回 `false`，`danger` 映射危险色确定按钮。
 */

import { createConfirmService, type ConfirmHandler, type ConfirmOptions } from '@bms/core'

export type { ConfirmHandler, ConfirmOptions } from '@bms/core'

const defaultHandler: ConfirmHandler = async (options) => {
  // Vant 对话框与样式按需加载（首次确认时拉取；避免未用到的宿主包体膨胀）
  const { showConfirmDialog } = await import('vant')
  await import('vant/es/dialog/style')
  try {
    await showConfirmDialog({
      title: options.title,
      message: options.message,
      confirmButtonText: options.confirmText ?? '确定',
      cancelButtonText: options.cancelText ?? '取消',
      confirmButtonColor: options.danger ? '#ee0a24' : undefined,
    })
    return true
  } catch {
    return false
  }
}

const service = createConfirmService(defaultHandler)

/** 覆盖确认实现（宿主自定义 UI；传 `undefined` 恢复默认 Vant 对话框） */
export function configureConfirm(next: ConfirmHandler | undefined): void {
  service.configure(next)
}

/** 弹确认框（默认 Vant `showConfirmDialog`） */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  return service.confirm(options)
}
