/**
 * 标签脏数据关闭确认（多标签导航 / 双层标签共用内部辅助）。
 *
 * **注入式**：确认弹窗实现由宿主 / 插件注入（`configureDirtyConfirm`；文案归注入实现）；
 * 未注入时按占位语义放行（不阻断）。
 */

export interface DirtyConfirmOptions {
  title: string
  message: string
  confirmText: string
  cancelText: string
}

export type DirtyConfirm = (options: DirtyConfirmOptions) => Promise<boolean>

let dirtyConfirm: DirtyConfirm | undefined

/** 注入脏数据确认实现（宿主 / ui-ep 弹窗能力接入时调用） */
export function configureDirtyConfirm(confirm: DirtyConfirm | undefined): void {
  dirtyConfirm = confirm
}

/** 关闭前脏数据确认：`enabled` 为假或非 dirty 或未注入确认实现时直接放行 */
export async function confirmDirtyClose(tab: { dirty?: boolean }, enabled: boolean): Promise<boolean> {
  if (!enabled || !tab.dirty || !dirtyConfirm) {
    return true
  }
  return dirtyConfirm({
    title: 'unsaved.title',
    message: 'unsaved.message',
    confirmText: 'unsaved.abandon',
    cancelText: 'unsaved.continueEdit',
  })
}
