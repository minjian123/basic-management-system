/** 确认对话框契约（框架无关）：渲染插件各自的 `confirm` 实现必须满足的接口面。 */

export interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  /** 危险语义（确定按钮 danger） */
  danger?: boolean
}

export type ConfirmHandler = (options: ConfirmOptions) => Promise<boolean>
