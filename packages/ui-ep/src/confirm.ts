/**
 * ui-ep 确认对话框注入点（宿主可覆盖；默认 ElMessageBox 实现）。
 *
 * 供弹窗关闭链（`useModalShell`）与标签脏数据确认（`confirmDirtyClose`）共用；
 * 未覆盖时使用 Element Plus `ElMessageBox`（真实可用，非占位放行）。
 */

import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'

export interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  /** 危险语义（确定按钮 danger） */
  danger?: boolean
}

export type ConfirmHandler = (options: ConfirmOptions) => Promise<boolean>

const defaultConfirm: ConfirmHandler = async (options) => {
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

let handler: ConfirmHandler | undefined

/** 覆盖确认实现（宿主自定义 UI；传 `undefined` 恢复默认） */
export function configureConfirm(next: ConfirmHandler | undefined): void {
  handler = next
}

/** 弹确认框（默认 ElMessageBox） */
export function confirm(options: ConfirmOptions): Promise<boolean> {
  return (handler ?? defaultConfirm)(options)
}
