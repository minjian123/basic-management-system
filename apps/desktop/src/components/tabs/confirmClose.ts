/**
 * 标签脏数据关闭确认（多标签导航 / 双层标签共用内部辅助）。
 *
 * 复用 `useConfirm`（`03_01`）与弹窗文案（`modal.unsaved*`）；返回是否放行关闭。
 */

import { i18n } from '@/i18n'
import { useConfirm } from '@/utils/useConfirm'

/** 关闭前脏数据确认：`enabled` 为假或非 dirty 时直接放行 */
export async function confirmDirtyClose(tab: { dirty?: boolean }, enabled: boolean): Promise<boolean> {
  if (!enabled || !tab.dirty) {
    return true
  }
  const t = i18n.global.t as unknown as (key: string) => string
  const { confirm } = useConfirm()
  return confirm({
    title: t('modal.unsavedTitle'),
    message: t('modal.unsavedMessage'),
    confirmText: t('modal.abandon'),
    cancelText: t('modal.continueEdit'),
  })
}
