/**
 * ui-ep 确认对话框注入点（宿主可覆盖；默认 ElMessageBox 实现）。
 *
 * 契约与覆盖 / 恢复语义单份在 `@bms/core`（`createConfirmService`）；供弹窗关闭链
 * （`useModalShell`）与标签脏数据确认（`confirmDirtyClose`）共用。
 */

import { createConfirmService, type ConfirmHandler, type ConfirmOptions } from '@bms/core'
import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'

export type { ConfirmHandler, ConfirmOptions } from '@bms/core'

const defaultHandler: ConfirmHandler = async (options) => {
  try {
    await ElMessageBox.confirm(options.message, options.title ?? '', {
      confirmButtonText: options.confirmText ?? '确定',
      cancelButtonText: options.cancelText ?? '取消',
      type: options.danger ? 'warning' : 'info',
      dangerouslyUseHTMLString: false,
    })
    return true
  } catch {
    return false
  }
}

const service = createConfirmService(defaultHandler)

/** 覆盖确认实现（宿主自定义 UI；传 `undefined` 恢复默认 ElMessageBox） */
export function configureConfirm(next: ConfirmHandler | undefined): void {
  service.configure(next)
}

/** 弹确认框（默认 ElMessageBox） */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  return service.confirm(options)
}
