/**
 * 确认组合式：轻量二次确认（删除 / 危险操作）。
 *
 * 契约见《组件设计 · 弹窗抽屉表单》§8：封装 `ElMessageBox.confirm`——统一 `warning` 语义、
 * 确定按钮 danger、**禁止点遮罩 / Esc 关闭**；返回 Promise（确认 `true` / 取消 `false`，不抛异常）；
 * `onConfirm` 异步期间按钮 loading、完成后自动关闭（抛错保留弹窗）；自定义正文 / 二次输入用 `ConfirmDialog`。
 */

import { ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message-box/style/css'

import { i18n } from '@/i18n'

/** 确认选项 */
export interface ConfirmOptions {
  /** 标题（缺省 i18n `modal.confirmTitle`） */
  title?: string
  /** 正文（说明后果，如「删除后不可恢复」） */
  message: string
  confirmText?: string
  cancelText?: string
  /** 危险语义：确定按钮 danger（缺省 true——删除 / 危险操作） */
  danger?: boolean
  /** 确认后回调（异步期间按钮 loading，完成后自动关闭；抛错保留弹窗供重试） */
  onConfirm?: () => void | Promise<void>
  /** 取消回调 */
  onCancel?: () => void
}

/** 确认组合式返回值 */
export interface UseConfirmReturn {
  confirm: (options: ConfirmOptions | string) => Promise<boolean>
}

/**
 * 获取确认能力。
 *
 * 用法：`const { confirm } = useConfirm(); if (await confirm({ message: t('modal.deleteConfirm') })) { … }`
 */
export function useConfirm(): UseConfirmReturn {
  const t = i18n.global.t as unknown as (key: string) => string

  async function confirm(options: ConfirmOptions | string): Promise<boolean> {
    const opts: ConfirmOptions = typeof options === 'string' ? { message: options } : options
    try {
      await ElMessageBox.confirm(opts.message, opts.title ?? t('modal.confirmTitle'), {
        type: 'warning',
        confirmButtonText: opts.confirmText ?? t('common.confirm'),
        cancelButtonText: opts.cancelText ?? t('common.cancel'),
        confirmButtonClass: opts.danger === false ? undefined : 'el-button--danger',
        closeOnClickModal: false,
        closeOnPressEscape: false,
        beforeClose: (action, instance, done) => {
          if (action === 'confirm' && opts.onConfirm) {
            instance.confirmButtonLoading = true
            void Promise.resolve(opts.onConfirm())
              .then(() => {
                instance.confirmButtonLoading = false
                done()
              })
              .catch(() => {
                instance.confirmButtonLoading = false
              })
            return
          }
          if (action !== 'confirm') {
            opts.onCancel?.()
          }
          done()
        },
      })
      return true
    } catch {
      return false
    }
  }

  return { confirm }
}
