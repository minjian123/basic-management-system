/**
 * 标签脏数据关闭确认（多标签导航 / 双层标签共用内部辅助）。
 *
 * 复用 ui-ep 确认注入点（`confirm`；默认 ElMessageBox）。文案为缺省中文，
 * 宿主经 i18n 覆盖确认实现时可自行取词。
 */

import { confirm } from '../../confirm'

/** 关闭前脏数据确认：`enabled` 为假或非 dirty 时直接放行 */
export async function confirmDirtyClose(tab: { dirty?: boolean }, enabled: boolean): Promise<boolean> {
  if (!enabled || !tab.dirty) {
    return true
  }
  return confirm({
    title: '未保存的修改',
    message: '有未保存的修改，确定放弃吗？',
    confirmText: '放弃修改',
    cancelText: '继续编辑',
    danger: true,
  })
}
